"""cXTML/1.0 conformance: every corpus card and example gets its expected verdict.

    python -m unittest discover tests -v

Each card `X.xtml` has `X.expect.json`:
    profile          validator profile (delegation | message | kimi)
    exit             the cXTML/1.0 verdict (0 valid; 1 = valid under the advisory profiles kimi/any; 2 invalid)
    reason           for invalid cards: a substring the diagnostic must contain (right verdict, right reason)

The implementation is validator/validate.py, the mirror of the upstream reference validator (it carries the
cXTML/1.0 literal regions and the App. F nesting depth since the 2026-10-01 sync).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["XTML_CARD_FORMAT"] = str(ROOT / "validator" / "card-format.json")
_MOD: list = []


def verdict(card: Path, profile: str) -> tuple[int, str]:
    """Run the validator in-process; return (exit code, all diagnostics)."""
    if not _MOD:
        spec = importlib.util.spec_from_file_location("cxtml_validate", ROOT / "validator" / "validate.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MOD.append(mod)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = _MOD[0].main([str(card), "--profile", profile])
    return rc, out.getvalue()


def cards(*dirs: str) -> list[Path]:
    return sorted(p for d in dirs for p in (ROOT / d).glob("*.xtml"))


class Conformance(unittest.TestCase):
    def test_corpus_size(self):
        self.assertGreaterEqual(len(cards("corpus/valid")), 30)
        self.assertGreaterEqual(len(cards("corpus/invalid")), 30)
        for card in cards("corpus/valid", "corpus/invalid", "examples"):
            self.assertTrue(card.with_suffix(".expect.json").is_file(), card.name)

    def test_every_card_gets_its_verdict(self):
        for card in cards("corpus/valid", "corpus/invalid", "examples"):
            exp = json.loads(card.with_suffix(".expect.json").read_text(encoding="utf-8"))
            with self.subTest(card=f"{card.parent.name}/{card.name}"):
                rc, diag = verdict(card, exp["profile"])
                self.assertEqual(rc, exp["exit"], diag)
                if exp.get("reason"):
                    self.assertIn(exp["reason"], diag)

    def test_valid_dir_holds_only_valid_verdicts(self):
        for card in cards("corpus/valid"):
            exp = json.loads(card.with_suffix(".expect.json").read_text(encoding="utf-8"))
            self.assertLess(exp["exit"], 2, card.name)
        for card in cards("corpus/invalid"):
            exp = json.loads(card.with_suffix(".expect.json").read_text(encoding="utf-8"))
            self.assertEqual(exp["exit"], 2, card.name)


if __name__ == "__main__":
    unittest.main()
