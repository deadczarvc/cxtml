"""Dialects: detection, declaration and the fixtures that prove a refusal.

    python -m pytest -q tests/test_dialects.py

The rule under test is the one in spec/DIALECTS.md: the dialect is decided by the first structural token, the
declaration must agree with the decision, and an undetermined dialect is a refusal. The fixtures carry their
declaration in `.expect.json`; a fixture that is meant to demonstrate a contradicted declaration says so with a
`dialect_violation` field, and then the disagreement is the expected result.
"""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("cxtml_dialect", ROOT / "tools" / "dialect.py")
DIALECT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DIALECT)

CARD_OPEN = re.compile(r"\[open\]\s*([A-Za-z][A-Za-z0-9._-]*)")


def fixtures() -> list[Path]:
    return sorted(
        list((ROOT / "corpus" / "valid").glob("*.xtml"))
        + list((ROOT / "corpus" / "invalid").glob("*.xtml"))
        + list((ROOT / "examples").glob("*.xtml"))
    )


def expectation(card: Path) -> dict:
    return json.loads(card.with_suffix(".expect.json").read_text(encoding="utf-8"))


class Detection(unittest.TestCase):
    def test_card_markers_make_a_card(self):
        self.assertEqual(DIALECT.detect('[open]task[sep]x[close]task[sep]')["dialect"], "xtml-card")

    def test_angle_tags_make_an_xml_doc(self):
        self.assertEqual(DIALECT.detect("<task><mission>x</mission></task>")["dialect"], "xml-doc")

    def test_earliest_token_wins_both_ways(self):
        self.assertEqual(DIALECT.detect("<a/>\n[open]b[sep]")["dialect"], "xml-doc")
        self.assertEqual(DIALECT.detect("[open]b[sep]\n<a/>")["dialect"], "xtml-card")

    def test_no_structural_token_is_unknown(self):
        found = DIALECT.detect("plain prose, no markup")
        self.assertEqual(found["dialect"], "unknown")
        self.assertIsNone(found["basis"]["card_marker_at"])
        self.assertIsNone(found["basis"]["angle_tag_at"])

    def test_basis_carries_offsets(self):
        found = DIALECT.detect("xx[open]a[sep]")
        self.assertEqual(found["basis"]["card_marker_at"], 2)
        self.assertEqual(found["basis"]["first_structural_token"], "[open]")


class Declaration(unittest.TestCase):
    def test_unknown_is_refused_even_without_a_declaration(self):
        bad = DIALECT.declaration_complaints("plain prose", "xtml-card")
        self.assertTrue(bad)
        self.assertIn("undetermined", bad[0])

    def test_contradiction_names_both_sides(self):
        bad = DIALECT.declaration_complaints("<a/>", "xtml-card")
        self.assertTrue(bad)
        self.assertIn("declared xtml-card", bad[0])
        self.assertIn("xml-doc", bad[0])

    def test_agreement_is_silent(self):
        self.assertEqual(DIALECT.declaration_complaints("[open]a[sep]", "xtml-card"), [])

    def test_declaration_outside_the_set_is_refused(self):
        self.assertTrue(DIALECT.declaration_complaints("[open]a[sep]", "yaml"))


class Fixtures(unittest.TestCase):
    def test_every_card_declares_its_dialect(self):
        for card in fixtures():
            self.assertTrue(card.with_suffix(".expect.json").is_file(), card.name)
            self.assertIn(expectation(card).get("dialect"), DIALECT.DIALECTS, card.name)

    def test_declaration_agrees_with_detection(self):
        for card in fixtures():
            exp = expectation(card)
            text = card.read_text(encoding="utf-8")
            if exp.get("dialect_violation"):
                self.assertTrue(
                    DIALECT.declaration_complaints(text, exp["dialect"]),
                    f"{card.name} declares a violation but the declaration and detection agree",
                )
            else:
                self.assertEqual(exp["dialect"], DIALECT.detect(text)["dialect"], card.name)

    def test_marked_violations_are_refused_by_the_card_validator(self):
        for card in fixtures():
            exp = expectation(card)
            if exp.get("dialect_violation"):
                self.assertEqual(exp["exit"], 2, card.name)


class XmlDoc(unittest.TestCase):
    def test_xml_fixtures_are_well_formed_and_declared_xml_doc(self):
        files = sorted((ROOT / "examples").glob("*.xml")) + sorted((ROOT / "corpus").glob("xml-doc/*.xml"))
        self.assertTrue(files, "no xml-doc fixture: the second dialect would exist only in prose")
        for path in files:
            exp = json.loads(path.with_suffix(".expect.json").read_text(encoding="utf-8"))
            self.assertEqual(exp["dialect"], "xml-doc", path.name)
            self.assertEqual(exp["exit"], 0, path.name)
            ET.parse(path)  # raises on malformed XML: that is the whole contract of this dialect

    def test_the_two_dialects_carry_the_same_tree(self):
        card = ROOT / "examples" / "delegation-card.xtml"
        xml = ROOT / "examples" / "xml-doc-card.xml"
        card_sections = set(CARD_OPEN.findall(card.read_text(encoding="utf-8")))
        xml_sections = {el.tag for el in ET.parse(xml).getroot()}
        self.assertTrue(card_sections, "the card fixture has no sections")
        self.assertEqual(card_sections - {"task"}, xml_sections, "the pair drifted apart")
        self.assertEqual(DIALECT.detect(card.read_text(encoding="utf-8"))["dialect"], "xtml-card")
        self.assertEqual(DIALECT.detect(xml.read_text(encoding="utf-8"))["dialect"], "xml-doc")


if __name__ == "__main__":
    unittest.main()
