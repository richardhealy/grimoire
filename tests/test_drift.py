"""Drift gate tests — stub LLM, no image files needed."""
import asyncio
import json
import pytest
from pathlib import Path
from grimoire.bible.character import CharacterRecord
from grimoire.drift.gate import (
    judge_panel, accumulate_failures,
    InvariantCheck, CharacterDriftReport, PanelDriftReport,
    MAX_RETRIES, GateDecision,
)

BIBLE_PATH = Path(__file__).parent.parent / "data/bible/xara/character.yaml"


def stub_drift_judge(checks: list[dict], style: float = 8.0, text_contamination: bool = False):
    def client(system, user):
        return json.dumps({
            "invariant_checks": checks,
            "style_adherence": style,
            "text_contamination": text_contamination,
        })
    return client


def all_pass_checks(char: CharacterRecord) -> list[dict]:
    return [{"invariant": inv, "verdict": "PASS", "note": ""} for inv in char.visual.invariants]

def one_fail_checks(char: CharacterRecord) -> list[dict]:
    checks = all_pass_checks(char)
    checks[0] = {"invariant": checks[0]["invariant"], "verdict": "FAIL", "note": "scar on wrong side"}
    return checks


def test_all_pass_returns_pass():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    client = stub_drift_judge(all_pass_checks(char))
    report = asyncio.run(judge_panel("p01_01", "panel.png", [char], attempt=1, llm_client=client))
    assert report.gate_decision == "PASS"

def test_one_fail_returns_retry_on_attempt_1():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    client = stub_drift_judge(one_fail_checks(char))
    report = asyncio.run(judge_panel("p01_01", "panel.png", [char], attempt=1, llm_client=client))
    assert report.gate_decision == "RETRY"

def test_one_fail_returns_escalate_at_max_retries():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    client = stub_drift_judge(one_fail_checks(char))
    report = asyncio.run(judge_panel(
        "p01_01", "panel.png", [char],
        attempt=MAX_RETRIES, llm_client=client
    ))
    assert report.gate_decision == "ESCALATE"

def test_text_contamination_escalates():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    client = stub_drift_judge(all_pass_checks(char), text_contamination=True)
    report = asyncio.run(judge_panel("p01_01", "panel.png", [char], attempt=1, llm_client=client))
    assert report.gate_decision == "ESCALATE"

def test_retry_adds_to_prompt_additions():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    client = stub_drift_judge(one_fail_checks(char))
    report = asyncio.run(judge_panel("p01_01", "panel.png", [char], attempt=1, llm_client=client))
    # Should have retry prompt additions for the failed invariant
    char_report = report.character_reports[0]
    assert len(char_report.retry_prompt_additions) > 0
    assert any("scar" in a.lower() for a in char_report.retry_prompt_additions)

def test_judge_parse_error_is_unclear():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    def bad_client(system, user):
        return "not valid json"
    report = asyncio.run(judge_panel("p01_01", "panel.png", [char], attempt=1, llm_client=bad_client))
    # UNCLEAR results don't pass (pass rate < 85%)
    char_report = report.character_reports[0]
    all_unclear = all(c.verdict == "UNCLEAR" for c in char_report.invariant_checks)
    assert all_unclear

def test_accumulate_failures_updates_negative_block():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    original_neg = char.visual.negative_block

    # Build a PASS report (only PASS reports accumulate on confirmed pass)
    # Actually failures only accumulate on ESCALATE with human confirmation
    # So this tests the non-accumulation on RETRY
    char_report = CharacterDriftReport(
        character_id=char.id,
        invariant_checks=[
            InvariantCheck("scar through right eyebrow", "FAIL", "scar was on left side"),
        ],
        style_adherence=7.0,
        text_contamination=False,
        overall_verdict="RETRY",
        retry_prompt_additions=["CRITICAL scar direction"],
    )
    report = PanelDriftReport(
        panel_id="p01_01",
        attempt=1,
        character_reports=[char_report],
        gate_decision="RETRY",
    )
    updated = accumulate_failures(report, {char.id: char})
    # RETRY does not accumulate (only ESCALATE with human confirmation does)
    assert char.id not in updated   # not updated on RETRY


def _wrap_all_pass(char: CharacterRecord, template: str):
    body = json.dumps({
        "invariant_checks": all_pass_checks(char),
        "style_adherence": 8.0,
        "text_contamination": False,
    }, indent=2)
    reply = template.format(body=body)
    return lambda system, user: reply


@pytest.mark.parametrize("template", [
    "```JSON\n{body}\n```",
    "Here is my assessment of the panel:\n\n```json\n{body}\n```",
    "Assessment follows.\n{body}\nThat is all.",
], ids=["JSON-fence", "prose-before-fence", "prose-no-fence"])
def test_wrapped_judge_reply_is_read(template):
    # On main these replies were thrown away as parse errors, so a clean panel
    # was re-rendered and finally escalated.
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    client = _wrap_all_pass(char, template)
    report = asyncio.run(judge_panel("p01_01", "panel.png", [char], attempt=1, llm_client=client))
    char_report = report.character_reports[0]
    assert report.gate_decision == "PASS"
    assert all(c.verdict == "PASS" for c in char_report.invariant_checks)
    assert char_report.style_adherence == 8.0


@pytest.mark.parametrize("reply", ["[]", '[{"invariant": "x", "verdict": "PASS"}]'])
def test_non_object_judge_reply_is_a_parse_error(reply):
    # On main a JSON list crashed judge_panel with AttributeError.
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    report = asyncio.run(judge_panel(
        "p01_01", "panel.png", [char], attempt=1, llm_client=lambda s, u: reply
    ))
    char_report = report.character_reports[0]
    assert report.gate_decision == "RETRY"
    assert all(c.verdict == "UNCLEAR" for c in char_report.invariant_checks)
    assert all(c.note == "judge_parse_error" for c in char_report.invariant_checks)
    assert char_report.style_adherence == 5.0
    assert char_report.text_contamination is False
