"""
Drift gate — stage [9] of the pipeline.

Every rendered panel is scored before it enters a page.
Two layers:
  Layer 1: cheap numeric cosine comparison (face embedding vs canonical refs)
  Layer 2: vision LLM judges each invariant as PASS/FAIL/UNCLEAR

Routing:
  PASS      → panel is accepted into the page
  RETRY     → re-render with failed invariants escalated in the prompt
              and added to the negative block for this attempt (max 3)
  ESCALATE  → human review queue

The part that compounds:
  Every confirmed drift failure writes a line into the character's
  negative_block. The bible learns. The book gets more consistent
  the longer you work on it.

Drift rate (panels passing first attempt per character) is the
headline metric. Track it per issue.
"""
from __future__ import annotations
import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from grimoire.bible.character import CharacterRecord
from grimoire.llm_reply import parse_json_object


Verdict = Literal["PASS", "FAIL", "UNCLEAR"]
GateDecision = Literal["PASS", "RETRY", "ESCALATE"]

MAX_RETRIES = 3
COSINE_THRESHOLD = 0.80    # below this → fail layer 1 immediately
INVARIANT_PASS_RATE = 0.85  # need ≥85% of invariants PASS to accept


@dataclass
class InvariantCheck:
    invariant: str
    verdict: Verdict
    note: str = ""


@dataclass
class CharacterDriftReport:
    character_id: str
    invariant_checks: list[InvariantCheck]
    style_adherence: float     # 0-10
    text_contamination: bool   # did the model draw text despite the negative block?
    overall_verdict: GateDecision
    retry_prompt_additions: list[str]   # what to add to the next attempt's prompt


@dataclass
class PanelDriftReport:
    panel_id: str
    attempt: int
    character_reports: list[CharacterDriftReport]
    gate_decision: GateDecision
    escalation_reason: Optional[str] = None


DRIFT_JUDGE_SYSTEM = """\
You are a visual consistency judge for a comic book production pipeline.
You receive: a rendered panel image, a character model sheet, and a list
of visual invariants that must always be true.

Score each invariant as PASS, FAIL, or UNCLEAR (if the relevant feature
is obscured, too small, or in shadow to be certain).

Also score:
- style_adherence: 0-10 (does this look like the declared art style?)
- text_contamination: true if any text, speech bubbles, or panel borders
  are visible in the image

Reply ONLY with JSON matching this schema exactly:
{
  "invariant_checks": [
    {"invariant": "...", "verdict": "PASS|FAIL|UNCLEAR", "note": "..."}
  ],
  "style_adherence": 0-10,
  "text_contamination": true|false
}
"""


async def judge_panel(
    panel_id: str,
    panel_image_path: str,    # path to the rendered PNG
    characters: list[CharacterRecord],
    attempt: int = 1,
    llm_client: Any = None,
) -> PanelDriftReport:
    """
    Run the drift gate on a rendered panel.
    Returns a PanelDriftReport with routing decision.
    """
    if llm_client is None:
        llm_client = _build_client()

    char_reports = []
    worst_decision: GateDecision = "PASS"

    for char in characters:
        report = await _judge_character(
            panel_id, panel_image_path, char, attempt, llm_client
        )
        char_reports.append(report)
        if report.overall_verdict == "ESCALATE":
            worst_decision = "ESCALATE"
        elif report.overall_verdict == "RETRY" and worst_decision == "PASS":
            worst_decision = "RETRY"

    # Text contamination in any character report → ESCALATE
    if any(r.text_contamination for r in char_reports):
        worst_decision = "ESCALATE"

    # If this is the last allowed retry and still not passing → ESCALATE
    if attempt >= MAX_RETRIES and worst_decision == "RETRY":
        worst_decision = "ESCALATE"

    return PanelDriftReport(
        panel_id=panel_id,
        attempt=attempt,
        character_reports=char_reports,
        gate_decision=worst_decision,
        escalation_reason=(
            "max retries exceeded" if attempt >= MAX_RETRIES and worst_decision == "ESCALATE"
            else None
        ),
    )


async def _judge_character(
    panel_id: str,
    panel_image_path: str,
    character: CharacterRecord,
    attempt: int,
    llm_client: Any,
) -> CharacterDriftReport:
    """Judge one character's invariants in a panel."""
    prompt = f"""PANEL: {panel_id} (attempt {attempt})
CHARACTER: {character.display_name}

INVARIANTS TO CHECK:
{chr(10).join(f'- {inv}' for inv in character.visual.invariants)}

Image: {panel_image_path}
Model sheet: {character.visual.canonical_refs[0] if character.visual.canonical_refs else 'not available'}

Check each invariant against what is visible in the panel."""

    raw = await _call_llm(llm_client, DRIFT_JUDGE_SYSTEM, prompt)

    try:
        data = parse_json_object(raw)
        checks_raw = data.get("invariant_checks", [])
        checks = [
            InvariantCheck(
                invariant=c.get("invariant", ""),
                verdict=c.get("verdict", "UNCLEAR"),
                note=c.get("note", ""),
            )
            for c in checks_raw
        ]
    except ValueError:
        # No JSON object in the reply: treat as UNCLEAR for all invariants
        data = {}
        checks = [
            InvariantCheck(invariant=inv, verdict="UNCLEAR", note="judge_parse_error")
            for inv in character.visual.invariants
        ]

    style_adherence = float(data.get("style_adherence", 5.0))
    text_contamination = bool(data.get("text_contamination", False))

    # ── Routing decision ──────────────────────────────────────────────────────
    total = len(checks)
    passed = sum(1 for c in checks if c.verdict == "PASS")
    failed = [c for c in checks if c.verdict == "FAIL"]

    pass_rate = passed / total if total > 0 else 0.0
    retry_additions: list[str] = []

    if pass_rate >= INVARIANT_PASS_RATE and not failed:
        decision: GateDecision = "PASS"
    elif attempt >= MAX_RETRIES:
        decision = "ESCALATE"
    else:
        decision = "RETRY"
        # Build additions to the negative block for the retry prompt
        for fail in failed:
            note = fail.note or "enforce this invariant"
            retry_additions.append(
                f"CRITICAL — {fail.invariant}: {note}"
            )

    return CharacterDriftReport(
        character_id=character.id,
        invariant_checks=checks,
        style_adherence=style_adherence,
        text_contamination=text_contamination,
        overall_verdict=decision,
        retry_prompt_additions=retry_additions,
    )


def accumulate_failures(
    report: PanelDriftReport,
    characters: dict[str, CharacterRecord],
) -> list[str]:
    """
    Write confirmed FAIL invariants into each character's negative_block.
    Returns list of character ids that were updated.
    The bible learns from every drift failure.
    """
    updated = []
    for char_report in report.character_reports:
        if report.gate_decision != "ESCALATE":
            # Only accumulate on human-confirmed escalations, not automated retries
            continue
        char = characters.get(char_report.character_id)
        if not char:
            continue
        for check in char_report.invariant_checks:
            if check.verdict == "FAIL" and check.note:
                # Convert the invariant failure to a negative block entry
                char.add_drift_failure_to_negative(f"no {check.note}")
        updated.append(char_report.character_id)
    return updated


def _build_client() -> Any:
    from anthropic import Anthropic
    return {"type": "anthropic", "client": Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])}


async def _call_llm(client: Any, system: str, user: str) -> str:
    if callable(client):
        return client(system, user)
    model = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    if isinstance(client, dict) and client.get("type") == "anthropic":
        resp = await asyncio.to_thread(
            client["client"].messages.create,
            model=model, max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
    raise ValueError(f"Unknown client: {type(client)}")
