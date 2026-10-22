"""Rules for the public documents added with this arc.

    python -m pytest -q tests/test_public_docs.py

Three properties, each of which has already failed somewhere in this contour:

  1. English only, no machine-local paths: a public document is not a dump of someone's workstation.
  2. Provenance on every claim: a numbered claim or a bullet carries [F|I|S]/grade, so a reader can weigh it.
  3. No placeholders: a document that says TODO is a promise, not a specification.

A markdown table row is exempt from rule 2 because the provenance lives in a column of that row.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    ROOT / "spec" / "VOCABULARY.md",
    ROOT / "spec" / "DIALECTS.md",
    ROOT / "spec" / "PLUGIN-CONTRACT.md",
    ROOT / "docs" / "A2A.md",
]
CLAIM = re.compile(r"^(?:- |\d+\. )")
MARKER = re.compile(r"\[(?:F|I|S)/(?:A|B|C\d?)(?::[^\]\n]*)?\]")
CYRILLIC = re.compile(r"[\u0400-\u04FF]")
MACHINE_PATH = re.compile(r"[A-Za-z]:[\\/]|/(?:home|Users)/|\\\\[A-Za-z0-9._-]+\\")
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b")


class PublicDocs(unittest.TestCase):
    def test_the_documents_exist(self):
        for doc in DOCS:
            self.assertTrue(doc.is_file(), doc)

    def test_english_only(self):
        for doc in DOCS:
            text = doc.read_text(encoding="utf-8")
            hit = CYRILLIC.search(text)
            self.assertIsNone(hit, f"{doc.name}: non-English character {hit.group(0)!r}" if hit else doc.name)

    def test_no_machine_local_paths(self):
        for doc in DOCS:
            for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                self.assertIsNone(MACHINE_PATH.search(line), f"{doc.name}:{n}: machine-local path")

    def test_every_claim_carries_provenance(self):
        for doc in DOCS:
            blocks = re.split(r"\n\s*\n", doc.read_text(encoding="utf-8"))
            for block in blocks:
                if not CLAIM.match(block):
                    continue
                where = block.strip().splitlines()[0][:70]
                self.assertRegex(block, MARKER, f"{doc.name}: claim without [F|I|S]/grade: {where}")

    def test_status_and_convention_are_declared(self):
        for doc in DOCS:
            text = doc.read_text(encoding="utf-8")
            self.assertIn("Status:", text, doc.name)
            self.assertIn("Provenance convention", text, doc.name)

    def test_no_placeholders(self):
        for doc in DOCS:
            self.assertIsNone(PLACEHOLDER.search(doc.read_text(encoding="utf-8")), doc.name)

    def test_the_spec_points_at_the_extension_documents(self):
        spec = (ROOT / "spec" / "SPEC.md").read_text(encoding="utf-8")
        for name in ("VOCABULARY.md", "DIALECTS.md", "PLUGIN-CONTRACT.md"):
            self.assertIn(name, spec, f"spec/SPEC.md does not point at spec/{name}")

    def test_recorded_gaps_are_named_where_they_belong(self):
        dialects = (ROOT / "spec" / "DIALECTS.md").read_text(encoding="utf-8")
        self.assertIn("quote-blind", dialects)
        vocabulary = (ROOT / "spec" / "VOCABULARY.md").read_text(encoding="utf-8")
        self.assertIn("not data-driven yet", vocabulary)


if __name__ == "__main__":
    unittest.main()
