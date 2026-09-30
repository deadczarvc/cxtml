"""cXTML/1.0 conformance: every corpus card and example gets its expected verdict.

    python -m unittest discover tests -v

Each card `X.xtml` has `X.expect.json`:
    profile          validator profile (delegation | message | kimi)
    exit             the cXTML/1.0 verdict (0 valid; 1 = valid under the advisory profiles kimi/any; 2 invalid)
    reference_exit   present only where the upstream reference validator still lags the spec
    reason           for invalid cards: a substring the diagnostic must contain (right verdict, right reason)

Two implementations run: validator/validate.py (mirror of the upstream reference) and
validator/proposed/validate.py (the reference plus the proposed cXTML/1.0 patch).
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
IMPLS = {"reference": ROOT / "validator" / "validate.py", "proposed": ROOT / "validator" / "proposed" / "validate.py"}
_MODS: dict[str, object] = {}


def verdict(impl: str, card: Path, profile: str) -> tuple[int, str]:
    """Run one implementation in-process; return (exit code, all diagnostics)."""
    if impl not in _MODS:
        spec = importlib.util.spec_from_file_location(f"cxtml_{impl}", IMPLS[impl])
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MODS[impl] = mod
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = _MODS[impl].main([str(card), "--profile", profile])
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
            for impl in IMPLS:
                want = exp["exit"] if impl == "proposed" else exp.get("reference_exit", exp["exit"])
                with self.subTest(card=f"{card.parent.name}/{card.name}", impl=impl):
                    rc, diag = verdict(impl, card, exp["profile"])
                    self.assertEqual(rc, want, diag)
                    if exp.get("reason") and want == exp["exit"]:
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
