# Changelog

## 2026-11-09

### Fixed

- The drift judge (stage 9) and the voice judge (stage 5) no longer throw
  away a good verdict because of how the model wrapped its JSON. Both used
  `.lstrip("```json")`, which strips any of the characters `` ` ``, `j`,
  `s`, `o` and `n` rather than the fence, so only a bare object or one
  fenced exactly as ```` ```json ```` was read. A reply fenced as
  ```` ```JSON ````, or with a sentence before or after the JSON, became
  `judge_parse_error`: every invariant UNCLEAR and a re-render for the drift
  gate, a failed line for the voice lock.
- A judge reply that is a JSON list no longer crashes `judge_panel` or
  `judge_line` with `AttributeError`; it is treated as a parse error.

### Added

- `grimoire/llm_reply.py`: `parse_json_object()` takes the JSON object out
  of a judge reply. It looks inside the first Markdown code fence first,
  then in the whole reply, and raises `ValueError` when there is no object.
- Tests for the parser and for wrapped and non-object replies in both
  judges (`tests/test_llm_reply.py`, `tests/test_drift.py`,
  `tests/test_voice.py`).

## 2026-10-06

### Fixed

- The package can now be built and installed, and the tests run from any
  checkout. The code moved from the repo root into `grimoire/`; before, the
  wheel build failed because hatchling found no `grimoire` package, and a
  clone into a folder not named `grimoire` failed to collect any tests with
  `No module named 'grimoire'`.
- `pyproject.toml` now declares PyYAML, so an installed wheel imports
  without a separate install step. The live Anthropic and Gemini clients are
  optional extras (`llm` and `gemini`).

### Added

- `tests/test_packaging.py`: checks the package sits where the build backend
  looks for it, and imports every module and runs the suite from a copy of
  the repo in a folder with another name.
- `PROGRESS.md` and this changelog.
