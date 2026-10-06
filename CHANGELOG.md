# Changelog

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
