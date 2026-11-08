"""Reading the JSON object out of an LLM judge reply."""

import json

import pytest

from grimoire.llm_reply import parse_json_object

OBJ = {"verdict": "PASS", "score": 0.9, "violations": []}
BODY = json.dumps(OBJ, indent=2)


@pytest.mark.parametrize(
    "raw",
    [
        BODY,
        f"  {BODY}\n",
        f"```json\n{BODY}\n```",
        f"```JSON\n{BODY}\n```",
        f"```Json\n{BODY}\n```",
        f"```\n{BODY}\n```",
        f"```json {BODY}```",
        f"Here is my assessment:\n\n```json\n{BODY}\n```",
        f"```json\n{BODY}\n```\nLet me know if you need more detail.",
        f"Assessment follows.\n{BODY}\nThat is all.",
    ],
    ids=[
        "bare",
        "whitespace",
        "json-fence",
        "JSON-fence",
        "Json-fence",
        "untagged-fence",
        "one-line-fence",
        "prose-before-fence",
        "prose-after-fence",
        "prose-no-fence",
    ],
)
def test_finds_the_object(raw):
    assert parse_json_object(raw) == OBJ


def test_keys_that_start_with_fence_letters_survive():
    # The old .lstrip("```json") stripped characters, not a prefix; check a
    # bare object is never trimmed.
    raw = '{"json": 1, "notes": "ok"}'
    assert parse_json_object(raw) == {"json": 1, "notes": "ok"}


def test_object_on_the_fence_line_is_read_whole():
    # A fence whose JSON starts on the same line as the tag is not a fenced
    # block; the nested objects inside must not be picked out on their own.
    nested = {
        "summary": {"verdict": "PASS"},
        "invariant_checks": [{"invariant": "scar", "verdict": "PASS"}],
        "style_adherence": 8,
    }
    raw = "```json " + json.dumps(nested, indent=2) + "\n```"
    assert parse_json_object(raw) == nested


def test_fence_wins_over_braces_in_the_prose():
    raw = "Checked {hair, scar}.\n```json\n" + BODY + "\n```"
    assert parse_json_object(raw) == OBJ


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not valid json",
        "[]",
        '[{"verdict": "PASS"}]',
        '"PASS"',
        "```json\n[1, 2]\n```",
        '```json\n{"verdict": "PASS", "score":\n',
    ],
    ids=[
        "empty",
        "prose",
        "empty-list",
        "list-of-objects",
        "string",
        "fenced-list",
        "truncated",
    ],
)
def test_raises_value_error_without_an_object(raw):
    with pytest.raises(ValueError):
        parse_json_object(raw)
