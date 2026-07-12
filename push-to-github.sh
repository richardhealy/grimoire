#!/usr/bin/env bash
set -euo pipefail
VISIBILITY="${VISIBILITY:-public}"
ORG="${ORG:-}"; owner=""; [ -n "$ORG" ] && owner="${ORG}/"
gh repo create "${owner}grimoire" --${VISIBILITY} --source=. --remote=origin --push \
  --description "Character-locked comic generator — versioned bible, deterministic prompt compiler, drift gate, SVG layout and lettering"
echo "Done: https://github.com/${owner}grimoire"
