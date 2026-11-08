"""
Reading the JSON object out of an LLM judge reply.

The drift judge (stage 9) and the voice judge (stage 5) are told to reply
with a bare JSON object, but models often wrap it in a Markdown code fence
(with any language tag, in any case, or none) or put a sentence before or
after it. parse_json_object takes the object out of any of those shapes, so
a good verdict is not thrown away as a parse error.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```[\w+-]*[ \t]*\n(.*?)```", re.DOTALL)
_JSON_START = re.compile(r"[{\[]")
_DECODER = json.JSONDecoder()


def parse_json_object(raw: str) -> dict[str, Any]:
    """Return the JSON object in an LLM reply.

    Looks first inside the first Markdown code fence, then in the whole
    reply. In each place it decodes from the first ``{`` or ``[`` and ignores
    any text after the value. Raises ValueError when neither place holds a
    JSON object: no JSON at all, a list or other non-object value, or an
    object cut off part way.
    """
    fence = _FENCE.search(raw)
    candidates = [fence.group(1), raw] if fence else [raw]
    for text in candidates:
        start = _JSON_START.search(text)
        if start is None:
            continue
        try:
            value, _ = _DECODER.raw_decode(text, start.start())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("no JSON object in the judge reply")
