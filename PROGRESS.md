# Progress

Status against the pipeline on the grimoire Notion page (12 stages). Checked
against the code on 2026-10-06.

## Pipeline stages

| # | Stage | State | Where |
|---|-------|-------|-------|
| 1 | Ingest and diarise (WhisperX) | Not built. The classifier takes utterances that are already diarised. | |
| 2 | Table-talk stripper | Built and tested | `grimoire/ingest/classifier.py` |
| 3 | Speaker map | Partly built: `classify_transcript` accepts a speaker map, but nothing builds one | `grimoire/ingest/classifier.py` |
| 4 | Beat sheet (human gate) | Not built. `intensity_curve()` gives a starting signal. | |
| 5 | Script with Voice Lock (human gate) | Rewriter, judge and `lock_dialogue` built and tested with fake clients; no human gate | `grimoire/script/voice.py` |
| 6 | Panel plan | `PanelSpec` type and its validation only; nothing turns a script into panels | `grimoire/bible/panel.py` |
| 7 | Prompt compiler | Built and tested (deterministic) | `grimoire/prompt/compiler.py` |
| 8 | Render | Stub renderer writes placeholder PNGs; the Gemini path is written but has never been run | `grimoire/render/stub.py` |
| 9 | Drift gate | Built and tested with fake clients, including negative-block accumulation | `grimoire/drift/gate.py` |
| 10 | Page layout (SVG) | Six-panel grid and splash built and tested | `grimoire/layout/page.py` |
| 11 | Lettering | Balloon placement and SVG overlay built and tested | `grimoire/letter/balloons.py` |
| 12 | Print export (PDF/X) | Not built | |

There is no entry point that runs the stages end to end: each stage is a
library function.

## Done

- 2026-10-06: the code now lives in a `grimoire/` package. Before, it sat at
  the repo root, so the wheel build failed and the tests only ran in a folder
  named `grimoire`. PyYAML is declared as a dependency, with `llm` and
  `gemini` extras for the live paths. 3 packaging tests added (70 in total).

## Known issues

- No README. The repo has no description of what it is, how to install it or
  how to run the tests.
- No CI workflow.
- `ruff check .` reports 60 findings, all from before this change: mostly
  unused imports and import order, plus `.lstrip("```json")` in
  `drift/gate.py` and `script/voice.py` (it strips a set of characters, not
  the prefix) and unused variables in three tests.
- `.gitignore` ignores `*.pdf`, so a dossier PDF under `docs/dossier/` will
  need an exception.
- The Notion page names `gemini-3.1-flash-image` as the target renderer; the
  Gemini path in `render/stub.py` has not been run against the live API.

## Next

1. README: what grimoire is, install, run the tests, status and limits.
2. CI: run pytest and ruff on push.
3. Dossier.
4. Stage 1, 4, 6 and 12 work, or an end-to-end runner over the stages that
   exist.
