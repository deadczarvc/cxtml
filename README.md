# cXTML

cXTML is a dialect of **XTML**, the markup of the Kimi K3 chat template, for multi-agent prompts on any model.

## Origin and credit

XTML is Moonshot AI's work: Kimi K3 technical report, arXiv 2607.24653, Appendix F, and the reference encoder
`encoding_k3.py` published with the Kimi K3 weights. XTML replaces the angle brackets of XML with reserved special
tokens (open, separator, close) plus an end-of-message stop marker, so every structural boundary is one token.
All credit for the notation belongs there. This repository does not redefine XTML; it pins down a dialect.

## What cXTML adds

On Kimi K3 the markers are real tokens. Written into a prompt for any other model they are ordinary characters, and
every guarantee that came from being a token is gone. cXTML restores a floor:

1. a quoting rule for markers inside text: code spans and fenced blocks are literal regions; attribute values use
   character references (`grammar/RULES.md` 1.6, 1.7);
2. two profiles beyond the original: `delegation` (task cards between agents, with a strict routing packet) and
   `message` (peer messages between agents, call / index correlation);
3. the obligation to validate before delivery to a model without the reserved tokens, with a reference validator
   and a conformance corpus.

Every document valid under App. F XTML (profile `kimi`) is valid cXTML.

## Layout

| path | content |
|---|---|
| `spec/SPEC.md` | the specification, GENERATED (rules + grammar + vocabulary) |
| `grammar/` | normative rules (`RULES.md`) and ABNF (`cxtml.abnf`); App. F vs cXTML origin marked per rule |
| `profiles/` | per-profile vocabulary, GENERATED from the validator |
| `validator/` | mirror of the upstream reference validator, pinned by `SOURCE.lock` |
| `corpus/valid`, `corpus/invalid` | conformance cards, one `.expect.json` verdict per card |
| `validator/codec.py` | reference codec (stdlib): one AST, a text renderer and a K3 token renderer, `parse` for both |
| `tests/` | conformance runner (`test_conformance.py`), codec round trips and differential checks (`test_codec.py`) |
| `examples/` | small annotated documents per profile |
| `tools/` | spec renderer, mirror sync check, sanitization gate |

## Run

```sh
python -m pip install regex
python tools/sync_validator.py          # mirror bytes match SOURCE.lock
python tools/render_spec.py --check     # generated files match their sources
python -m unittest discover tests -v    # every card gets its expected verdict
python tools/sanitize_scan.py           # 0 hits
```

The reference validator is maintained in Russian; its diagnostics are Russian, and the `reason` substrings in
`corpus/**/*.expect.json` quote them. Exit codes are the language-neutral contract: 0 clean, 1 advisory, 2 malformed.

## Status

cXTML/1.0, unreleased. Licenses are a DEFAULT pending the owner's decision: Apache-2.0 for code, CC-BY-4.0 for the
specification text (see `LICENSE`).
