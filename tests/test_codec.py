"""cXTML codec tests (W68 2026-10-01): AST truth, text and K3 renderers, round trips, differential checks.

    python -B -m unittest discover -s <this dir> -v        (ops tree: tools/xtml/tests; repo: tests/)

Locations are found relative to this file: codec.py and validate.py sit next to tests/ (ops tree) or in validator/ (repo).
The corpus comes from <repo>/corpus (repo layout) or env CXTML_REPO. encoding_k3.py (Moonshot, not redistributed here)
comes from env XTML_ENCODING_K3 (a copy of huggingface.co/moonshotai/Kimi-K3 encoding_k3.py); a missing input skips its tests, never passes them.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
BASE = HERE.parent if (HERE.parent / "codec.py").is_file() else HERE.parent / "validator"
REPO = HERE.parent if (HERE.parent / "corpus").is_dir() else Path(os.environ.get("CXTML_REPO", "/nonexistent"))
if (BASE / "card-format.json").is_file() and "XTML_CARD_FORMAT" not in os.environ:
    os.environ["XTML_CARD_FORMAT"] = str(BASE / "card-format.json")
sys.path.insert(0, str(BASE))
from codec import CodecError, Doc, Element, _dec, el, parse, render


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve their module by name
    spec.loader.exec_module(mod)
    return mod


VALIDATE = load(BASE / "validate.py", "cxtml_validate_for_codec")
K3_PATH = Path(os.environ.get("XTML_ENCODING_K3", ""))  # unset: Path("") is not a file, the K3 tests skip
CARDS = (
    sorted(p for d in ("corpus/valid", "corpus/invalid", "examples") for p in (REPO / d).glob("*.xtml"))
    if REPO.is_dir()
    else []
)
need_corpus = unittest.skipUnless(CARDS, "corpus not found (set CXTML_REPO)")


def expect(card: Path) -> dict:
    return json.loads(card.with_suffix(".expect.json").read_text(encoding="utf-8"))


# validate.scan refusals that are semantic, not structural (the codec does not build on them): the declared gap
SEMANTIC = (
    "повторяется",
    "обязательный раздел",
    "значение атрибута",
    "управляющие символы",
    "нет ни одного элемента",
    "вложен сам в себя",
)


def walk(e: Element, depth: int = 1):
    yield e.name, depth, dict(e.attrs)
    for c in e.children:
        if isinstance(c, Element):
            yield from walk(c, depth + 1)


def verdict(text: str, profile: str) -> int:
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "x.xtml"
        f.write_text(text, encoding="utf-8", newline="")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return VALIDATE.main([str(f), "--profile", profile])


def one(text: str) -> Element:
    return parse(text).root


class Semantics(unittest.TestCase):
    def test_a_quoted_marker_never_becomes_structure(self) -> None:
        root = one("[open]a[sep]x `[close]a[sep]` y `[end_of_msg]` z[close]a[sep]")
        self.assertEqual(root, el("a", (), "x [close]a[sep] y [end_of_msg] z"))
        fenced = one("[open]a[sep]\n```\n[close]a[sep]\n[open]b[sep]\n```\nend[close]a[sep]")
        self.assertEqual(fenced.children, ("\n[close]a[sep]\n[open]b[sep]\nend",))
        tilde = one("[open]a[sep]\n~~~~\n[open]b[sep]\n~~~\n~~~~\n[close]a[sep]")
        self.assertEqual(tilde.text(), "\n[open]b[sep]\n~~~\n")

    def test_a_span_without_a_marker_is_ordinary_text_and_keeps_its_backticks(self) -> None:
        self.assertEqual(one("[open]a[sep]run `python -m x` now[close]a[sep]").text(), "run `python -m x` now")

    def test_an_unclosed_code_span_does_not_escape(self) -> None:
        self.assertEqual(one("[open]a[sep]x `y[close]a[sep]").text(), "x `y")
        self.assertEqual(one("[open]a[sep]``two `one[close]a[sep]").text(), "``two `one")
        cross_paragraph = "[open]a[sep]`open\n\nclosed` [close]a[sep]"
        self.assertEqual(one(cross_paragraph).text(), "`open\n\nclosed` ")  # the span dies at the blank line
        self.assertEqual(one("[open]a[sep]\n```\nnever closed\n[close]a[sep]").text(), "\n```\nnever closed\n")

    def test_negative_control_a_raw_marker_in_text_is_an_error_in_text_form(self) -> None:
        for raw in (
            "[open]a[sep]x [close]a[sep] y [close]a[sep]",  # the first close ends the root, the rest is text
            "[open]a[sep]x [end_of_msg] y[close]a[sep]",  # stop marker inside an element
            "[open]a[sep]x [sep] y[close]a[sep]",  # separator without an open / close
            "[open]a[sep]x [open]b[sep] y[close]a[sep]",  # b is never closed
            "[open]a[sep]x[close]a[sep][open]b[sep]y[close]b[sep]",  # a second root
        ):
            with self.subTest(raw), self.assertRaises(CodecError):
                parse(raw)
        ast = el("a", (), "x [close]a[sep] y")  # the same text as data: the renderer quotes it
        naive = "[open]a[sep]x [close]a[sep] y[close]a[sep]\n"
        self.assertEqual(render(ast), "[open]a[sep]`x [close]a[sep] y`[close]a[sep]\n")
        with self.assertRaises(CodecError):
            parse(naive)

    def test_text_references_outside_quotes(self) -> None:
        """Rule 1.6.9 (W73): &#96; &#126; &#38; decode in one pass in text outside quotes; quote content stays verbatim."""
        self.assertEqual(
            one("[open]a[sep]&#96; &#126; &#38;#96; &amp; &#91;[close]a[sep]").text(), "` ~ &#96; &amp; &#91;"
        )
        self.assertEqual(one("[open]a[sep]`[close] &#96;`[close]a[sep]").text(), "[close] &#96;")  # a quote: verbatim
        self.assertEqual(one("[open]a[sep]`&#96;`[close]a[sep]").text(), "```")  # marker-free span = ordinary text
        for s in ("&#96;", "&#38;", "&&#126;;", "&#38;#96; ` ~~~ [close]", "&#9", "&#96"):
            with self.subTest(s):
                self.assertEqual(parse(render(el("a", (), s))), Doc(el("a", (), s)))

    def test_attribute_entities(self) -> None:
        root = one('[open]a id="q &#91;close] &amp;#91; &quot;x&quot; &amp;"[sep][close]a[sep]')
        self.assertEqual(root.attr("id"), 'q [close] &#91; "x" &')
        for value in (
            'say "hi" & [open]',
            "&#91;",
            "&amp;#91;",
            "&quot;",
            "[open][sep][close][end_of_msg]",
            "",
            "é ü 中",
        ):
            ast = el("a", {"id": value})
            with self.subTest(value):
                self.assertEqual(parse(render(ast)).root, ast)
                self.assertEqual(parse(render(ast, "k3")).root, ast)
        with self.assertRaises(CodecError):
            parse('[open]a id="x [close] y"[sep][close]a[sep]')  # a raw marker in a value is refused, as validate.py
        self.assertNotIn("[close]", render(el("a", {"id": "x [close] y"})).split("[sep]")[0])

    def test_k3_channel_is_separate_from_text(self) -> None:
        ast = el("a", {"id": "[open] <|open|>"}, "<|sep|> [close] <|end_of_msg|>")
        segs = render(ast, "k3")
        self.assertEqual(
            [s for s in segs if s[1]], [("<|open|>", True), ("<|sep|>", True), ("<|close|>", True), ("<|sep|>", True)]
        )
        self.assertIn(("<|sep|> [close] <|end_of_msg|>", False), segs)  # text, special tokens disallowed
        self.assertEqual(parse(segs).root, ast)
        self.assertEqual(
            one("[open]a[sep]<|open|> <|close|>[close]a[sep]").text(), "<|open|> <|close|>"
        )  # text, not marker
        with self.assertRaises(CodecError):
            parse([("<|open|>", True), ("a", False), ("<|close|>", True)])  # unknown nesting of control tokens
        with self.assertRaises(CodecError):
            parse([("<|image|>", True)])

    def test_pad_and_paragraphs(self) -> None:
        for leaf in (
            "`[close]`",
            " [close] ",
            "[close] `",
            "a\n\nb [open] c\n\nd",
            "x [sep]\n \ny [sep]",
            "``[end_of_msg]``",
        ):
            ast = el("a", (), leaf)
            with self.subTest(leaf):
                self.assertEqual(parse(render(ast)).root, ast)
        self.assertEqual(render(el("a", (), "`[close]`")), "[open]a[sep]`` `[close]` ``[close]a[sep]\n")

    def test_structure_errors(self) -> None:
        for bad in (
            "[open]a[sep]",
            "[open]a[sep][close]b[sep]",
            '[open]a k="1" k="2"[sep][close]a[sep]',
            "[open]a b=1[sep][close]a[sep]",
            "[open]а[sep][close]а[sep]",  # Cyrillic a: not ASCII
            "[close]a[sep]",
            "[sep]",
            "just text",
            "[open]a[sep][close]a[sep] tail",
            "[open]a[sep][close]a[sep][end_of_msg][end_of_msg]",
            "[end_of_msg][open]a[sep][close]a[sep]",
        ):
            with self.subTest(bad), self.assertRaises(CodecError):
                parse(bad)
        for bad_ast in (el("1a"), el("a", {"b c": "1"}), el("a", (), el("b", (("k", "1"), ("k", "2"))))):
            with self.subTest(bad_ast), self.assertRaises(CodecError):
                render(bad_ast)
        with self.assertRaises(CodecError):
            render(el("a"), "xml")

    def test_normal_form(self) -> None:
        self.assertEqual(Element("a", (), ("x", "", "y", Element("b"), "", "z")).children, ("xy", Element("b"), "z"))
        self.assertEqual(
            one("[open]a[sep]  [open]b[sep][close]b[sep]\n[close]a[sep]").children, ("  ", Element("b"), "\n")
        )
        doc = parse("preamble\n[open]a[sep][close]a[sep]\n[end_of_msg]\n")
        self.assertTrue(doc.eom)
        self.assertTrue(doc.warnings)
        self.assertEqual(parse(render(doc)), doc)

    def test_mutation_without_the_quote_the_self_check_refuses(self) -> None:
        codec = sys.modules["codec"]
        with (
            mock.patch.object(codec, "_text_leaf", lambda s: s),
            mock.patch.object(codec, "_escaped_leaf", lambda s: s),
            self.assertRaises(CodecError),
        ):
            render(el("a", (), "x [close]a[sep] y"))  # both mutated spellings emit a raw marker; render refuses

    def test_mutation_escaped_spelling_without_escapes_is_refused(self) -> None:
        pair = el("a", (), el("b", (), "x `"), el("c", (), "` y"))
        with mock.patch.object(sys.modules["codec"], "_escaped_leaf", lambda s: s), self.assertRaises(CodecError):
            render(pair)  # the fallback is guarded by the same self-check, not trusted

    def test_cross_structure_pairing_gets_the_escaped_spelling(self) -> None:
        """W73 (X11.14): the class W68 refused now has a faithful text form; the plain spelling still fails for it."""
        fence = el("a", (), el("b", (), "\n```\n"), el("c", (), "\n```\n"))
        for doc in (
            el("a", (), el("b", (), "x `"), el("c", (), "` y")),
            fence,
            el("a", (), "\n~~~\n", el("b"), "\n~~~\n"),
        ):
            with self.subTest(doc=doc):
                plain: list = []
                sys.modules["codec"]._text_el(doc, plain)
                with contextlib.suppress(CodecError):
                    self.assertNotEqual(parse("".join(plain)), Doc(doc))  # plain spelling is not faithful here
                text = render(doc)
                self.assertNotIn("`", text.replace("&#96;", ""))  # no raw backtick left to pair
                self.assertEqual(parse(text), Doc(doc))
                self.assertEqual(parse(render(doc, "k3")), Doc(doc))
        self.assertEqual(
            render(el("a", (), el("b", (), "x `"), el("c", (), "` y [close]"))),
            "[open]a[sep][open]b[sep]x &#96;[close]b[sep][open]c[sep]&#96; y `[close]`[close]c[sep][close]a[sep]\n",
        )


@unittest.skipUnless(K3_PATH.is_file(), "encoding_k3.py not found (set XTML_ENCODING_K3)")
class AgainstEncodingK3(unittest.TestCase):
    """Segment for segment: what encoding_k3.build_chat_segments emits for messages equals render(ast, 'k3')."""

    def test_conversation(self) -> None:
        enc = load(K3_PATH, "encoding_k3_under_test")
        messages = [
            {"role": "system", "content": "be terse"},
            {"role": "user", "name": 'a"b&c', "content": "hi [close] <|open|> `x`"},
            {
                "role": "assistant",
                "content": "ok",
                "tool_calls": [
                    {"id": "1", "function": {"name": "read_file", "arguments": {"path": 'a&b "q"', "n": 3}}}
                ],
            },
            {"role": "tool", "tool_call_id": "1", "content": "result [end_of_msg]"},
        ]
        want = [(s.text, s.allow_special) for s in enc.build_chat_segments(messages, add_generation_prompt=False)]

        def msg(attrs, *children):
            return Doc(el("message", attrs, *children), True)

        docs = [
            msg({"role": "system"}, "be terse"),
            msg({"role": "user", "name": 'a"b&c'}, "hi [close] <|open|> `x`"),
            msg(
                {"role": "assistant"},
                el("think"),
                el("response", (), "ok"),
                el(
                    "tools",
                    (),
                    el(
                        "call",
                        {"tool": "read_file", "index": "1"},
                        el("argument", {"key": "path", "type": "string"}, 'a&b "q"'),
                        el("argument", {"key": "n", "type": "number"}, "3"),
                    ),
                ),
            ),
            msg({"role": "tool", "tool": "read_file", "index": "1"}, "result [end_of_msg]"),
        ]
        got = [s for d in docs for s in render(d, "k3")]
        self.assertEqual(got, want)
        self.assertEqual([parse(render(d, "k3")) for d in docs], docs)


@need_corpus
class Corpus(unittest.TestCase):
    def test_round_trip_over_the_whole_corpus(self) -> None:
        parsed = 0
        for card in CARDS:
            text = card.read_text(encoding="utf-8")
            try:
                doc = parse(text)
            except CodecError:
                continue  # a structurally broken card has no AST; the differential test below owns that verdict
            parsed += 1
            with self.subTest(card=f"{card.parent.name}/{card.name}"):
                self.assertEqual(parse(render(doc, "k3")), doc)
                self.assertEqual(parse(render(doc, "text")), doc)
        self.assertGreaterEqual(parsed, 140)

    def test_the_rendered_card_keeps_its_validator_verdict(self) -> None:
        for card in CARDS:
            exp = expect(card)
            if exp["exit"] == 2:
                continue
            with self.subTest(card=f"{card.parent.name}/{card.name}"):
                rendered = render(parse(card.read_text(encoding="utf-8")), "text")
                self.assertEqual(verdict(rendered, exp["profile"]), exp["exit"])

    def test_same_structure_as_the_validator_scan(self) -> None:
        """Differential: codec.parse and validate.scan agree on structure for every corpus card; where scan refuses
        for a structural reason the codec raises. Semantic-only refusals (scan flags them, the codec does not build on
        them) are the declared gap."""
        for card in CARDS:
            text = card.read_text(encoding="utf-8")
            with self.subTest(card=f"{card.parent.name}/{card.name}"):
                rep = VALIDATE.scan(text, set(), True, strict_gaps=False, max_depth=99)
                structural = [e for e in rep.errors if not any(s in e for s in SEMANTIC)]
                try:
                    doc = parse(text)
                except CodecError:
                    self.assertTrue(rep.errors, "codec refused a document the validator scan accepted")
                    continue
                self.assertEqual(structural, [], "codec built an AST from a document the validator scan refuses")
                mine = [(t, d, a) for t, d, a in walk(doc.root)]
                theirs = [(t, d, {k: _dec(v, True) for k, v in a.items()}) for t, d, a in rep.elems]
                # scan stops at its first refusal, so after a semantic stop its element list is a prefix of ours
                self.assertEqual(theirs, mine[: len(theirs)] if rep.errors else mine)


class Generated(unittest.TestCase):
    """Property tests over seeded random ASTs (deterministic)."""

    WORDS = (
        "alpha",
        "b-c",
        "x.y",
        "  ",
        "\n",
        "é",
        "中文",
        "&",
        '"',
        "&amp;",
        "&#91;",
        "<|open|>",
        "<|sep|>",
    )
    MARKERS = (
        "[open]",
        "[sep]",
        "[close]",
        "[end_of_msg]",
        "[open]a[sep]",
        "[close]a[sep]",
    )
    BLANKS = (
        "\n\n",
        "\n \n",
        "\n\t\n\n",
    )

    def leaf(self, rng: random.Random, hostile: bool) -> str:
        pool = [*self.WORDS, *self.MARKERS, *self.MARKERS, *self.BLANKS]
        if hostile:
            pool += ["`", "``", "```", "~~~", "\n```\n", "\n~~~\n", " `x` "]
        return "".join(rng.choice(pool) for _ in range(rng.randint(1, 7)))

    def tree(self, rng: random.Random, hostile: bool, depth: int = 0) -> Element:
        kids = []
        for _ in range(rng.randint(0, 4)):
            kids.append(
                self.leaf(rng, hostile) if depth > 2 or rng.random() < 0.5 else self.tree(rng, hostile, depth + 1)
            )
        attrs = {f"k{i}": self.leaf(rng, False).replace("\n", " ") for i in range(rng.randint(0, 3))}
        return el(rng.choice(["a", "b.c", "d-e", "f_g"]), attrs, *kids)

    def test_marker_rich_trees_always_round_trip_in_both_forms(self) -> None:
        rng = random.Random(6801)
        for n in range(400):
            ast = Doc(self.tree(rng, hostile=False), eom=bool(n % 2))
            with self.subTest(n=n):
                self.assertEqual(parse(render(ast, "text")), ast)
                self.assertEqual(parse(render(ast, "k3")), ast)

    def test_hostile_trees_always_round_trip_in_both_forms(self) -> None:
        """W73 (X11.14): 600 / 600 in text form (W68: refusals for cross-structure pairing). The escaped spelling is
        exercised, not assumed, and validate.scan reads every rendered text with the same structure as the codec."""
        rng = random.Random(6802)
        escaped = 0
        for n in range(600):
            ast = Doc(self.tree(rng, hostile=True), eom=bool(n % 2))
            with self.subTest(n=n):
                self.assertEqual(parse(render(ast, "k3")), ast)  # K3 is total
                text = render(ast, "text")
                self.assertEqual(parse(text), ast)
                escaped += "&#96;" in text or "&#126;" in text
                rep = VALIDATE.scan(text, set(), True, strict_gaps=False, max_depth=99)
                self.assertEqual([e for e in rep.errors if not any(x in e for x in SEMANTIC)], [])
                mine = list(walk(ast.root))
                theirs = [(t, d, {k: _dec(v, True) for k, v in a.items()}) for t, d, a in rep.elems]
                self.assertEqual(theirs, mine[: len(theirs)] if rep.errors else mine)
        self.assertGreater(escaped, 50)  # the fallback carries a real share of the hostile set

    def texts(self, e: Element):
        for c in e.children:
            if isinstance(c, str):
                yield c
            else:
                yield from self.texts(c)


if __name__ == "__main__":
    unittest.main()
