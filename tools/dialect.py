#!/usr/bin/env python3
"""Which dialect is this document: `xtml-card` (token markup) or `xml-doc` (angle tags)?

    python tools/dialect.py FILE                 # one decision, machine-readable
    python tools/dialect.py --declared xml-doc FILE   # + the declaration check

Exit codes of this tool, and what each one means:

    0  the dialect is decided, the declaration (when given) agrees, and an `xml-doc` document is well formed
    1  `xml-doc` that is not well formed: the dialect's only contract fails, so the answer is a refusal
    2  the dialect is undetermined, or the declaration contradicts the detection

An `xml-doc` verdict is the well-formedness check itself (spec/DIALECTS.md §2), so it MUST NOT come back clean on a
document the XML parser rejects: that would be the silent OK this repository exists to prevent.

The rule is taken from the reference tooling, not invented here: the dialect is decided by the FIRST
structural token in document order, never by the file extension or the file name, and the decision carries
the two offsets it was made from so a wrong verdict can be argued with instead of guessed at (upstream
plugin `dsh-xtml`, `detectDialect`, 2026-10-22).

    card markers   [open] [sep] [close] [end_of_msg]
    angle tags     <name ...>  </name>   (a letter, then letters, digits, `.`, `_`, `:`, `-`)

`unknown` is a refusal, not a pass: a text with neither token is not a document of either dialect, and
reporting it as valid would be the silent OK that spec/DIALECTS.md forbids.

LIMIT: detection reads raw text, so a marker spelling quoted inside a code span still counts. That is
stated in spec/DIALECTS.md as a known gap, not papered over here.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DIALECTS = ("xtml-card", "xml-doc", "unknown")
CARD_RE = re.compile(r"\[(?:open|sep|close|end_of_msg)\]")
ANGLE_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9._:-]*(?=[\s/>])")


def detect(text: str) -> dict:
    """Decision plus its basis: offsets of the first card marker and the first angle tag."""
    card = CARD_RE.search(text or "")
    angle = ANGLE_RE.search(text or "")
    card_at = card.start() if card else -1
    angle_at = angle.start() if angle else -1
    if card_at < 0 and angle_at < 0:
        return {"dialect": "unknown", "basis": {"card_marker_at": None, "angle_tag_at": None,
                                                "decided_by": "no structural token"}}
    dialect = "xtml-card" if card_at >= 0 and (angle_at < 0 or card_at < angle_at) else "xml-doc"
    first = (card or angle).group(0)
    return {
        "dialect": dialect,
        "basis": {
            "card_marker_at": None if card_at < 0 else card_at,
            "angle_tag_at": None if angle_at < 0 else angle_at,
            "decided_by": "earliest structural token",
            "first_structural_token": first,
        },
    }


def xml_well_formed(text: str) -> tuple[bool, str | None]:
    """The verdict of the `xml-doc` dialect: well-formedness, nothing more and nothing less.

    A schema, a namespace or a content model is not checked here — inventing one would promise more than the
    dialect says (spec/DIALECTS.md §2 and §6). A document the parser rejects returns the parser's own message, so
    the caller gets a refusal that names its cause instead of a bare verdict.
    """
    parser = ET.XMLParser()
    try:
        parser.feed(text or "")
        parser.close()
    except ET.ParseError as exc:
        return False, str(exc)
    return True, None


def declaration_complaints(text: str, declared: str) -> list[str]:
    """Refusals of the declaration rule (spec/DIALECTS.md): an undeclared or contradicted dialect."""
    bad: list[str] = []
    if declared not in DIALECTS:
        bad.append(f"declared dialect {declared!r} is not one of {', '.join(DIALECTS)}")
        return bad
    found = detect(text)
    if found["dialect"] == "unknown":
        bad.append("dialect is undetermined: the text carries neither a card marker nor an angle tag, "
                   "so there is nothing to check and a silent OK is forbidden")
    elif found["dialect"] != declared:
        bad.append(f"declared {declared}, but the first structural token makes it {found['dialect']} "
                   f"({found['basis']['first_structural_token']} at offset "
                   f"{found['basis']['card_marker_at'] if found['dialect'] == 'xtml-card' else found['basis']['angle_tag_at']})")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="detect the XTML dialect of a document")
    ap.add_argument("path", type=Path)
    ap.add_argument("--declared", choices=DIALECTS, help="declaration to check against the detection")
    a = ap.parse_args(argv)
    text = a.path.read_text(encoding="utf-8", errors="replace")
    found = detect(text)
    out = {"path": a.path.as_posix(), **found}
    rc = 0
    if found["dialect"] == "unknown":
        rc = 2
    if found["dialect"] == "xml-doc":
        well_formed, error = xml_well_formed(text)
        out["well_formed"] = well_formed
        if not well_formed:
            out["xml_error"] = error
            rc = 1
    if a.declared:
        bad = declaration_complaints(text, a.declared)
        out["declared"] = a.declared
        out["complaints"] = bad
        out["declaration_ok"] = not bad
        if bad:
            rc = 2
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
