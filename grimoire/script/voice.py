"""
Voice lock — stage [5] of the pipeline.

Two components:
  VoiceRewriter  — rewrites raw player dialogue into the character's voice
  VoiceJudge     — scores the rewritten line against the voice card
                   and rejects anything that violates never_says or lexicon_no

The rewriter preserves intent and information. The judge enforces identity.

Critical detail from spec §6:
  "The voice judge must compare characters *against each other*, not just
   against their own card. Reject lines that could belong to two PCs."
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Any
from grimoire.bible.character import CharacterRecord, VoiceCard
from grimoire.llm_reply import parse_json_object


@dataclass
class VoiceJudgement:
    passed: bool
    score: float              # 0-1
    violations: list[str]     # which rules were broken
    could_belong_to: list[str]  # other character ids this could sound like
    rewritten_line: str


REWRITER_SYSTEM = """\
You are a comic book dialogue writer. Rewrite the player's raw utterance
into the character's voice, using the voice card provided.

Rules:
- Preserve ALL information and intent from the original
- Apply the character's register, cadence, and lexicon
- Never use words from lexicon_no
- Never violate never_says
- Keep it short — comic panels have limited space
- Do NOT add information that wasn't in the original utterance

Reply with only the rewritten line. No quotes, no explanation.
"""

JUDGE_SYSTEM = """\
You are a voice consistency judge for a comic book. Evaluate whether a
dialogue line matches a character's voice card.

Reply ONLY with a JSON object matching this schema:
{
  "score": 0.0-1.0,
  "violations": ["list of specific rule violations, empty if none"],
  "could_belong_to_others": ["other character ids this could plausibly belong to"],
  "verdict": "PASS" or "FAIL"
}
"""


async def rewrite_line(
    raw_text: str,
    character: CharacterRecord,
    context: str = "",
    llm_client: Any = None,
) -> str:
    """
    Rewrite a raw player utterance into the character's voice.
    Returns the rewritten line.
    """
    if llm_client is None:
        llm_client = _build_client()

    voice = character.voice
    prompt = f"""CHARACTER: {character.display_name}
Register: {voice.register}
Cadence: {voice.cadence}
Words to use: {voice.lexicon_yes}
Words to avoid: {voice.lexicon_no}
Never says: {voice.never_says}
Voice tics: {voice.tics}
Example gold lines:
{chr(10).join(f'- {g}' for g in voice.gold_lines)}

{'Context: ' + context if context else ''}

RAW UTTERANCE: {raw_text}

Rewrite this in the character's voice:"""

    return await _call_llm(llm_client, REWRITER_SYSTEM, prompt)


async def judge_line(
    line: str,
    character: CharacterRecord,
    all_characters: list[CharacterRecord],
    llm_client: Any = None,
) -> VoiceJudgement:
    """
    Judge whether a line sounds like this character and only this character.
    """
    if llm_client is None:
        llm_client = _build_client()

    voice = character.voice
    others_summary = "\n".join(
        f"- {c.display_name}: {c.voice.register}"
        for c in all_characters
        if c.id != character.id
    )

    prompt = f"""EVALUATING LINE FOR: {character.display_name}

Voice card:
- Register: {voice.register}
- Cadence: {voice.cadence}
- never_says: {voice.never_says}
- lexicon_no: {voice.lexicon_no}
- lexicon_yes: {voice.lexicon_yes}

Other characters in the cast:
{others_summary}

LINE TO EVALUATE: "{line}"

Score this line. Does it sound like {character.display_name} and nobody else?"""

    raw = await _call_llm(llm_client, JUDGE_SYSTEM, prompt)

    try:
        data = parse_json_object(raw)
        return VoiceJudgement(
            passed=data.get("verdict", "FAIL") == "PASS",
            score=float(data.get("score", 0.0)),
            violations=data.get("violations", []),
            could_belong_to=data.get("could_belong_to_others", []),
            rewritten_line=line,
        )
    except ValueError:
        # No JSON object in the reply, or a score that is not a number
        return VoiceJudgement(
            passed=False, score=0.0,
            violations=["judge_parse_error"],
            could_belong_to=[],
            rewritten_line=line,
        )


async def lock_dialogue(
    raw_text: str,
    character: CharacterRecord,
    all_characters: list[CharacterRecord],
    context: str = "",
    max_attempts: int = 2,
    llm_client: Any = None,
) -> tuple[str, VoiceJudgement]:
    """
    Full voice lock pipeline: rewrite then judge, retry once if failing.
    Returns (final_line, judgement).
    """
    for attempt in range(max_attempts):
        rewritten = await rewrite_line(raw_text, character, context, llm_client)

        # Quick deterministic pre-check before calling the judge
        quick_violations = _quick_check(rewritten, character.voice)
        if quick_violations:
            if attempt < max_attempts - 1:
                raw_text = f"[REVISION NEEDED - avoid: {quick_violations}] {raw_text}"
                continue
            judgement = VoiceJudgement(
                passed=False, score=0.3,
                violations=quick_violations,
                could_belong_to=[],
                rewritten_line=rewritten,
            )
            return rewritten, judgement

        judgement = await judge_line(rewritten, character, all_characters, llm_client)
        if judgement.passed or attempt == max_attempts - 1:
            return rewritten, judgement

    return rewritten, judgement  # type: ignore[return-value]


def _quick_check(line: str, voice: VoiceCard) -> list[str]:
    """Deterministic pre-check before calling the LLM judge."""
    violations = []
    line_lower = line.lower()
    for word in voice.lexicon_no:
        if word.lower() in line_lower:
            violations.append(f"lexicon_no: '{word}'")
    for phrase in voice.never_says:
        # Use at least 3 meaningful words (skip short/common words) to avoid false positives
        kws = [w for w in phrase.lower().split() if len(w) > 3][:3]
        if kws and all(kw in line_lower for kw in kws):
            violations.append(f"never_says pattern: '{phrase[:40]}'")
    return violations


def _build_client() -> Any:
    import os
    from anthropic import Anthropic
    return {"type": "anthropic", "client": Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])}


async def _call_llm(client: Any, system: str, user: str) -> str:
    import os
    if callable(client):
        return client(system, user)
    if isinstance(client, dict) and client.get("type") == "anthropic":
        resp = await asyncio.to_thread(
            client["client"].messages.create,
            model=os.getenv("LLM_MODEL", "claude-sonnet-4-6"),
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
    raise ValueError(f"Unknown client: {type(client)}")
