"""cXTML codec (W68 2026-10-01): one AST, two surface forms. stdlib only.

    parse(text)      -> Doc   text form: bracket markers, literal regions (cXTML/1.0 rule 1.6), attribute entities (1.7)
    parse(segments)  -> Doc   K3 token form: [(string, allow_special)], as encoding_k3.EncodeSegment
    render(doc, "text") -> str
    render(doc, "k3")   -> [(string, allow_special)]   segment for segment what encoding_k3.py emits

AST = truth. Element(name, attrs, children), a child is an Element or a text leaf (adjacent leaves merge, "" is dropped);
Doc(root, eom). Text form quotes a text paragraph that holds a reserved marker spelling in a code span whose backtick run
is longer than any run inside it (one CommonMark pad space when the text starts / ends with a backtick; outer whitespace stays outside) and
writes `[` of a marker spelling inside an attribute value as &#91;. parse strips exactly those quotes: a literal region
WITHOUT a marker inside is ordinary text, its backticks stay. K3 needs no escaping: control tokens carry structure, text
segments (allow_special False) carry everything else (encoding_k3.py: _control / _text, _escape_attr_value).

render(doc, "text") re-parses its own output. When the plain spelling is not faithful (a raw backtick run or ~~~ / ```
fence line in marker-free text pairs with another across structure, W73 2026-10-01) it falls back to the escaped
spelling: outside quotes every ` is &#96;, every ~ is &#126;, & is &#38; where it begins one of these three references
(cXTML/1.0 rule 1.6.9, decoded by parse in all text outside quotes, one left-to-right pass), and each run of marker
spellings is its own one-backtick quote. No raw backtick or tilde is left to open a literal region, so the escaped
spelling exists for every AST; the self-check (parse(out) == doc) still guards both spellings and raises CodecError.
Structural validation (vocabulary, profiles) stays in validate.py; this is the one parser the tools use for content.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

OPEN, SEP, CLOSE, EOM = "[open]", "[sep]", "[close]", "[end_of_msg]"
K3 = {"<|open|>": OPEN, "<|sep|>": SEP, "<|close|>": CLOSE, "<|end_of_msg|>": EOM}
K3_OF = {v: k for k, v in K3.items()}
NAME = r"[A-Za-z][A-Za-z0-9._-]*"  # ASCII by construction, as validate.py
MARKER = re.compile(r"\[open\]|\[sep\]|\[close\]|\[end_of_msg\]")
OPEN_PAYLOAD = re.compile(rf'({NAME})((?:\s+{NAME}="[^"]*")*)')
ATTR = re.compile(rf'({NAME})="([^"]*)"')
NAME_RE = re.compile(NAME)
LITERAL_OPEN = re.compile(r"(?m)^ {0,3}(?P<fence>`{3,}(?=[^`\n]*$)|~{3,})|(?P<ticks>`+)")
TICKS = re.compile(r"`+")
BLANK_LINE = re.compile(r"\n[ \t]*\n")
MARKER_OPENING_BRACKET = re.compile(r"\[(?=(?:open|sep|close|end_of_msg)\])")
MARKER_RUN = re.compile(r"((?:\[open\]|\[sep\]|\[close\]|\[end_of_msg\])+)")
TEXT_REF = re.compile(r"&#(96|126|38);")  # rule 1.6.9: text outside quotes; one pass, so &#38;#96; reads as &#96;
TEXT_REF_AMP = re.compile(r"&(?=#(?:96|126|38);)")


class CodecError(ValueError):
    pass


@dataclass(frozen=True)
class Element:
    name: str
    attrs: tuple = ()
    children: tuple = ()

    def __post_init__(self) -> None:
        pairs = tuple((str(k), str(v)) for k, v in (self.attrs.items() if isinstance(self.attrs, dict) else self.attrs))
        merged: list = []
        for c in self.children:
            if isinstance(c, str):
                if c and merged and isinstance(merged[-1], str):
                    merged[-1] += c
                elif c:
                    merged.append(c)
            else:
                merged.append(c)
        object.__setattr__(self, "attrs", pairs)
        object.__setattr__(self, "children", tuple(merged))

    def attr(self, key: str, default: str | None = None) -> str | None:
        return next((v for k, v in self.attrs if k == key), default)

    def text(self) -> str:
        """The direct text leaves, concatenated."""
        return "".join(c for c in self.children if isinstance(c, str))

    def find(self, name: str) -> list[Element]:
        return [c for c in self.children if isinstance(c, Element) and c.name == name]


@dataclass(frozen=True)
class Doc:
    root: Element
    eom: bool = False
    warnings: tuple = field(default=(), compare=False)


def el(name: str, attrs=(), *children) -> Element:
    return Element(name, attrs, children)


def _pos(text: str, i: int) -> str:
    return f"line {text.count(chr(10), 0, i) + 1}, col {i - (text.rfind(chr(10), 0, i) + 1) + 1}"


def _dec(v: str, text_form: bool) -> str:
    """Attribute value decoding: text form &#91; &quot; &amp; (amp last); K3 only &quot; &amp; (encoding_k3._escape_attr_value)."""
    if text_form:
        v = v.replace("&#91;", "[")
    return v.replace("&quot;", '"').replace("&amp;", "&")


def _enc(v: str, text_form: bool) -> str:
    v = v.replace("&", "&amp;").replace('"', "&quot;")
    return MARKER_OPENING_BRACKET.sub("&#91;", v) if text_form else v


def _header(payload: str, text_form: bool, where: str) -> tuple[str, tuple]:
    m = OPEN_PAYLOAD.fullmatch(payload.strip())
    if not m:
        raise CodecError(f"{where}: element header does not parse: {payload.strip()[:60]!r}")
    attrs: list = []
    for k, v in ATTR.findall(m.group(2)):
        if any(k == a for a, _ in attrs):
            raise CodecError(f"{where}: attribute {k!r} repeated in element {m.group(1)!r}")
        if text_form and re.search(r"\[open\]|\[close\]|\[end_of_msg\]", v):
            raise CodecError(f"{where}: reserved marker inside the value of {k!r}; write &#91; for its bracket")
        attrs.append((k, _dec(v, text_form)))
    return m.group(1), tuple(attrs)


# --- literal regions (same rule as validate.py _literal_end; differential test in tests) -------------------------


def _literal_end(text: str, lo: re.Match) -> int | None:
    if lo.group("fence"):
        run = lo.group("fence")
        close = re.compile(rf"(?m)^ {{0,3}}{re.escape(run[0])}{{{len(run)},}}[ \t]*$")
        nl = text.find("\n", lo.end())
        m = close.search(text, nl + 1) if nl != -1 else None
        return m.end() if m else None
    n = len(lo.group("ticks"))
    para = BLANK_LINE.search(text, lo.end())
    for t in TICKS.finditer(text, lo.end(), para.start() if para else len(text)):
        if len(t.group(0)) == n:
            return t.end()
    return None


def _tdec(s: str) -> str:
    return TEXT_REF.sub(lambda m: chr(int(m.group(1))), s)


def _unquote(region: str, fence: bool) -> str:
    """The text a quote stands for: a code span minus its backtick runs (and one CommonMark pad space), a fence minus its two lines."""
    if fence:
        first, last = region.find("\n"), region.rfind("\n")
        return region[first + 1 : last] if last > first else ""
    n = len(TICKS.match(region).group(0))
    c = region[n:-n]
    return c[1:-1] if len(c) > 1 and c[0] == c[-1] == " " and c.strip(" ") else c


# --- text form -> AST --------------------------------------------------------------------------------------------


def _parse_text(text: str) -> Doc:
    stack: list[list] = []  # [name, attrs, children]
    root, eom, warns, pend = None, False, [], []
    i = mark = 0

    def gap(upto: int, at: int) -> None:
        pend.append(_tdec(text[mark:upto]))
        g = "".join(pend)
        pend.clear()
        if stack:
            stack[-1][2].append(g)
        elif g.strip():
            if root is not None or eom:
                raise CodecError(f"{_pos(text, at)}: text after the root element: {g.strip()[:50]!r}")
            warns.append(f"{_pos(text, at)}: text before the root is not part of the document")

    while True:
        m = MARKER.search(text, i)
        lo = LITERAL_OPEN.search(text, i) if m else None
        if lo and lo.start() < m.start():
            end = _literal_end(text, lo)
            if end is None:  # an opener without its closer escapes nothing
                i = lo.end()
                continue
            region = text[lo.start() : end]
            if MARKER.search(region):
                pend.append(_tdec(text[mark : lo.start()]))
                pend.append(_unquote(region, bool(lo.group("fence"))))  # quote content: never decoded
                mark = end
                warns.append(f"{_pos(text, lo.start())}: reserved marker inside a literal region: text, not markup")
            i = end
            continue
        at = m.start() if m else len(text)
        gap(at, at)
        if not m:
            break
        kind = m.group(0)
        if eom:
            raise CodecError(f"{_pos(text, at)}: {kind} after {EOM}; the stop marker must be last")
        if kind == EOM:
            if stack or root is None:
                raise CodecError(f"{_pos(text, at)}: {EOM} only after the closed root element")
            eom = True
            i = mark = m.end()
            continue
        if root is not None and not stack:
            raise CodecError(f"{_pos(text, at)}: markup after the root element was closed")
        if kind == SEP:
            raise CodecError(f"{_pos(text, at)}: {SEP} without a preceding {OPEN} or {CLOSE}")
        sep = text.find(SEP, m.end())
        if sep == -1:
            raise CodecError(f"{_pos(text, at)}: {kind} is not closed by {SEP}")
        if kind == OPEN:
            name, attrs = _header(text[m.end() : sep], True, _pos(text, at))
            stack.append([name, attrs, []])
        else:
            name = text[m.end() : sep].strip()
            if not NAME_RE.fullmatch(name):
                raise CodecError(f"{_pos(text, at)}: a close tag holds only the element name, found {name[:60]!r}")
            if not stack or stack[-1][0] != name:
                raise CodecError(
                    f"{_pos(text, at)}: {CLOSE}{name} does not match the open element {stack[-1][0] if stack else None!r}"
                )
            done = Element(*stack.pop())
            if stack:
                stack[-1][2].append(done)
            else:
                root = done
        i = mark = sep + len(SEP)
    if stack:
        raise CodecError(f"element {stack[-1][0]!r} is opened and never closed")
    if root is None:
        raise CodecError("no element in the document")
    return Doc(root, eom, tuple(warns))


# --- K3 token form -> AST ----------------------------------------------------------------------------------------


def _seg(s) -> tuple[str, bool]:
    return (s.text, s.allow_special) if hasattr(s, "allow_special") else (s[0], bool(s[1]))


def _parse_k3(segments) -> Doc:
    stack: list[list] = []
    root, eom, head, buf = None, False, None, []

    def flush() -> None:
        g = "".join(buf)
        buf.clear()
        if stack:
            stack[-1][2].append(g)
        elif g.strip():
            raise CodecError(f"text outside the root element: {g.strip()[:50]!r}")

    for n, s in enumerate(segments):
        text, special = _seg(s)
        if not special:
            (head[1] if head else buf).append(text)
            continue
        tok = K3.get(text)
        if tok is None or (head and tok != SEP) or eom:
            raise CodecError(f"segment {n}: unexpected control segment {text!r}")
        if tok == SEP:
            if not head:
                raise CodecError(f"segment {n}: {text} without an open or close token")
            kind, parts = head
            head = None
            if kind == OPEN:
                name, attrs = _header("".join(parts), False, f"segment {n}")
                stack.append([name, attrs, []])
            else:
                name = "".join(parts).strip()
                if not stack or stack[-1][0] != name:
                    raise CodecError(f"segment {n}: close {name!r} does not match {stack[-1][0] if stack else None!r}")
                done = Element(*stack.pop())
                if stack:
                    stack[-1][2].append(done)
                else:
                    root = done
            continue
        flush()
        if tok == EOM:
            if stack or root is None:
                raise CodecError(f"segment {n}: {text} only after the closed root element")
            eom = True
        elif root is not None and not stack:
            raise CodecError(f"segment {n}: markup after the root element was closed")
        else:
            head = (tok, [])
    flush()
    if head or stack or root is None:
        raise CodecError("K3 segments end inside an element or carry no element")
    return Doc(root, eom)


def parse(src) -> Doc:
    """str = text form; a list of (string, allow_special) / EncodeSegment = K3 token form."""
    return _parse_text(src) if isinstance(src, str) else _parse_k3(list(src))


# --- AST -> text form / K3 ---------------------------------------------------------------------------------------


def _check(e: Element) -> None:
    if not NAME_RE.fullmatch(e.name):
        raise CodecError(f"element name {e.name!r} is not [A-Za-z][A-Za-z0-9._-]*")
    keys = [k for k, _ in e.attrs]
    if len(set(keys)) != len(keys) or not all(NAME_RE.fullmatch(k) for k in keys):
        raise CodecError(f"attribute names of {e.name!r} must be unique names: {keys}")
    for c in e.children:
        if isinstance(c, Element):
            _check(c)


def _quote(piece: str) -> str:
    """Quote the core of a paragraph; its outer whitespace stays outside, so the card keeps its layout."""
    core = piece.strip(" \t\r\n")
    at = piece.index(core)
    n = max((len(r) for r in TICKS.findall(core)), default=0) + 1
    pad = " " if core[0] == "`" or core[-1] == "`" else ""
    return piece[:at] + "`" * n + pad + core + pad + "`" * n + piece[at + len(core) :]


def _text_leaf(s: str) -> str:
    """A paragraph with a reserved marker spelling goes into a code span; the blank-line gaps stay outside (a span lives in one paragraph)."""
    parts = re.split(r"(\n[ \t]*\n)", s)
    return "".join(p if i % 2 or not MARKER.search(p) else _quote(p) for i, p in enumerate(parts))


def _escaped_leaf(s: str) -> str:
    """Escaped spelling (rule 1.6.9): no raw ` or ~ outside quotes; each marker run is a one-backtick quote."""
    parts = MARKER_RUN.split(s)
    return "".join(
        f"`{p}`" if i % 2 else TEXT_REF_AMP.sub("&#38;", p).replace("`", "&#96;").replace("~", "&#126;")
        for i, p in enumerate(parts)
    )


def _text_el(e: Element, out: list, escaped: bool = False) -> None:
    out.append(f"{OPEN}{e.name}" + "".join(f' {k}="{_enc(v, True)}"' for k, v in e.attrs) + SEP)
    for c in e.children:
        if isinstance(c, str):
            out.append(_escaped_leaf(c) if escaped else _text_leaf(c))
        else:
            _text_el(c, out, escaped)
    out.append(f"{CLOSE}{e.name}{SEP}")


def _k3_el(e: Element, out: list) -> None:
    def add(s: str, special: bool = False) -> None:
        if s:
            out.append((s, special))

    add(K3_OF[OPEN], True)
    add(e.name)
    for k, v in e.attrs:
        add(f" {k}")
        add('="')
        add(_enc(v, False))
        add('"')
    add(K3_OF[SEP], True)
    for c in e.children:
        if isinstance(c, str):
            add(c)
        else:
            _k3_el(c, out)
    add(K3_OF[CLOSE], True)
    add(e.name)
    add(K3_OF[SEP], True)


def render(doc, target: str = "text"):
    d = doc if isinstance(doc, Doc) else Doc(doc)
    _check(d.root)
    out: list = []
    if target == "k3":
        _k3_el(d.root, out)
        if d.eom:
            out.append((K3_OF[EOM], True))
        return out
    if target != "text":
        raise CodecError(f"unknown target {target!r}: text | k3")
    why = ""
    for escaped in (False, True):  # plain spelling first (byte-stable for real cards), escaped spelling as fallback
        out = []
        _text_el(d.root, out, escaped)
        text = "".join(out) + ("\n" + EOM if d.eom else "") + "\n"
        try:
            if _parse_text(text) == d:
                return text
            why = "the re-parsed text differs from the AST"
        except CodecError as exc:
            why = str(exc)
    raise CodecError(f"no faithful text form (plain and escaped spellings both fail the self-check): {why}")


def main(argv: list[str]) -> int:
    """`codec.py <file> [text|k3]`: parse the text form, print the canonical rendering (rc 2 on a parse error)."""
    if not argv:
        print(main.__doc__)
        return 2
    try:
        d = parse(Path(argv[0]).read_text(encoding="utf-8"))
        out = render(d, argv[1] if len(argv) > 1 else "text")
    except (OSError, CodecError) as e:
        print(f"codec: {e}", file=sys.stderr)
        return 2
    print(out if isinstance(out, str) else "\n".join(repr(s) for s in out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
