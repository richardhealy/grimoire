"""Voice lock tests — stub LLM."""
import asyncio
import json
import pytest
from pathlib import Path
from grimoire.bible.character import CharacterRecord
from grimoire.script.voice import rewrite_line, judge_line, lock_dialogue, _quick_check

BIBLE_PATH = Path(__file__).parent.parent / "data/bible/xara/character.yaml"


def stub_rewriter(response: str):
    def client(system, user): return response
    return client

def stub_judge(score: float, violations: list, verdict: str, could_belong: list = None):
    def client(system, user):
        return json.dumps({
            "score": score,
            "violations": violations,
            "could_belong_to_others": could_belong or [],
            "verdict": verdict,
        })
    return client


def test_quick_check_catches_lexicon_no():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    violations = _quick_check("That was absolutely amazing!", char.voice)
    assert any("amazing" in v for v in violations)
    assert any("absolutely" in v for v in violations)

def test_quick_check_passes_clean_line():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    violations = _quick_check("Don't. Whatever it is, don't.", char.voice)
    assert violations == []

def test_rewrite_calls_llm():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    result = asyncio.run(
        rewrite_line("I think we should check the door", char,
                     llm_client=stub_rewriter("You want a plan or you want it done?"))
    )
    assert result == "You want a plan or you want it done?"

def test_judge_pass():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    judgement = asyncio.run(
        judge_line(
            "I've been in worse rooms.",
            char, [char],
            llm_client=stub_judge(0.95, [], "PASS"),
        )
    )
    assert judgement.passed is True
    assert judgement.score == 0.95

def test_judge_fail_on_violation():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    judgement = asyncio.run(
        judge_line(
            "I am honestly so sorry, this is an amazing situation.",
            char, [char],
            llm_client=stub_judge(0.2, ["lexicon_no: 'honestly'", "lexicon_no: 'amazing'"], "FAIL"),
        )
    )
    assert judgement.passed is False
    assert len(judgement.violations) == 2

def test_judge_rejects_ambiguous_line():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    judgement = asyncio.run(
        judge_line(
            "That's an interesting point.",
            char, [char],
            llm_client=stub_judge(0.4, [], "FAIL",
                                  could_belong=["kellan", "the_dark_lady"]),
        )
    )
    assert len(judgement.could_belong_to) > 0

def test_lock_dialogue_retries_on_violation():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    call_count = [0]
    responses = [
        "I honestly feel like this is an amazing journey.",  # violates lexicon_no
        "Worth it.",                                          # clean
    ]
    judge_responses = [
        json.dumps({"score": 0.2, "violations": ["absolutely"], "could_belong_to_others": [], "verdict": "FAIL"}),
        json.dumps({"score": 0.9, "violations": [], "could_belong_to_others": [], "verdict": "PASS"}),
    ]

    rewrite_idx = [0]
    judge_idx = [0]

    def rewrite_client(system, user):
        r = responses[min(rewrite_idx[0], len(responses)-1)]
        rewrite_idx[0] += 1
        return r

    def judge_client(system, user):
        r = judge_responses[min(judge_idx[0], len(judge_responses)-1)]
        judge_idx[0] += 1
        return r

    # Use judge client for both by checking system prompt
    def combined_client(system, user):
        if "voice consistency judge" in system:
            return judge_client(system, user)
        return rewrite_client(system, user)

    line, judgement = asyncio.run(
        lock_dialogue(
            "I think we should go through the door",
            char, [char],
            llm_client=combined_client,
            max_attempts=2,
        )
    )
    # Should have retried at least once
    assert rewrite_idx[0] >= 1

def test_lock_dialogue_malformed_judge_response():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    def client(system, user):
        if "consistency judge" in system:
            return "not valid json"
        return "Don't."
    line, judgement = asyncio.run(
        lock_dialogue("test", char, [char], llm_client=client)
    )
    assert "judge_parse_error" in judgement.violations


@pytest.mark.parametrize("template", [
    "```JSON\n{body}\n```",
    "Here is my verdict:\n\n```json\n{body}\n```",
    "Verdict follows.\n{body}\nThat is all.",
], ids=["JSON-fence", "prose-before-fence", "prose-no-fence"])
def test_wrapped_judge_reply_is_read(template):
    # On main these replies were thrown away as parse errors, so a good line
    # failed the voice lock.
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    body = json.dumps({
        "score": 0.95, "violations": [], "could_belong_to_others": [], "verdict": "PASS",
    }, indent=2)
    reply = template.format(body=body)
    judgement = asyncio.run(
        judge_line("I've been in worse rooms.", char, [char], llm_client=lambda s, u: reply)
    )
    assert judgement.passed is True
    assert judgement.score == 0.95
    assert judgement.violations == []


@pytest.mark.parametrize("reply", ["[]", '["PASS"]'])
def test_non_object_judge_reply_is_a_parse_error(reply):
    # On main a JSON list crashed judge_line with AttributeError.
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    judgement = asyncio.run(
        judge_line("I've been in worse rooms.", char, [char], llm_client=lambda s, u: reply)
    )
    assert judgement.passed is False
    assert judgement.violations == ["judge_parse_error"]
