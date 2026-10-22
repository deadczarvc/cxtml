# Changelog

## cXTML/1.0 (2026-10-03, `v1.0.0`)

- Rules and ABNF for the text form, each rule marked App. F, reference encoder, or cXTML extension.
- Two surface forms of the markers (bracket text form, K3 control tokens) and the bijection between them.
- Close tag = close marker + element name + separator; a bare close marker is invalid.
- Literal regions: CommonMark-style code spans and fenced blocks make reserved markers inside them text.
- Attribute values: `&amp;` and `&quot;` as in the reference encoder, plus `&#91;` for a quoted marker.
- Profiles `kimi`, `delegation` (routing v2), `message`; vocabulary generated from the reference validator.
- Conformance corpus with one expected verdict per card; valid cards include structure-preserving neutralizations of
  real delegation cards.
- Reference codec `validator/codec.py` (stdlib): `parse` for the text form and for K3 segments into one AST, `render`
  to the text form (quotes markers, escapes attribute values, refuses documents with no faithful text form) and to K3
  segments exactly as `encoding_k3.py` emits them; round-trip, differential and mutation tests in `tests/test_codec.py`.
- Validator mirror pinned by `SOURCE.lock`. The reference validator carries the literal regions and the App. F nesting
  depth for profile `kimi` (merged 2026-10-01; there is no proposal patch any more).
- Profile `message` aligned with `encoding_k3.py` (2026-10-01): `role="peer"` (cXTML extension), `call` with `tool` +
  `index`, `argument` with `key` + `type` (`name` = deprecated alias, warns), a reply that answers a call carries its
  `tool` + `index`.

- Profile `doc` (2026-10-01): documents that are not cards (program, plan, summary). Root `doc` or `task`, closed
  vocabulary owned by the `doc` block of `card-format.json` (an element outside it is exit 2), no mandatory sections, no
  end-of-message marker; clean is exit 0. Corpus: 3 valid and 5 invalid `doc-*` cards.
- Profile `doc` (2026-10-03, additive): root `handoff` and nine elements for track handoffs (`done-this-wave`,
  `git-blocker`, `handoff`, `next-action`, `peers`, `remaining`, `status`, `track-dir`, `verify`); the vocabulary
  moved to the validator's module `vocab.py`.
- Text references (rule 1.6.9, 2026-10-01): `&#96;`, `&#126;`, `&#38;` decode in content outside quotes. The codec
  keeps the plain spelling wherever it reads back (byte-identical to the previous writer) and otherwise writes the
  escaped spelling, so the text form is total: the 600 hostile generated trees the codec used to refuse in part now
  round-trip 600 / 600, and `validate.scan` reads every rendered text with the codec's structure.

## Unreleased (2026-10-22): station experience

- `spec/VOCABULARY.md`: the dictionary as data. One data file plus a schema, two generated projections
  (`card-format.json` and the `PHASES` line) that must never be edited by hand, and one growth tool with three
  operations (`add-tag`, `add-phase`, `add-enum-value`), a dry run that writes nothing, three gates on apply, a backup
  and a rollback, an append-only journal, a strict-superset assertion, and no removal by automation. A tag added to a
  required list is refused, because it would change the fate of historical cards.
- `spec/DIALECTS.md`: `xtml-card` (token markup, checked against a profile) and `xml-doc` (angle tags, well-formedness
  only), the rule that the first structural token decides the dialect, and the requirement that a document's dialect be
  declared and agree with that decision. The known gap (detection is quote-blind) is recorded, not hidden.
- `spec/PLUGIN-CONTRACT.md`: the validator, the profile registry and the card generator as three tools with 4, 0 and 2
  parameters; why the schemas are flat (per-call cost, a JSON node ceiling at the boundary); the refusal table that makes
  a false OK impossible, including a missing engine, an empty registry that exited 0, an absent phase list, and input
  above the ceiling refused rather than truncated.
- `docs/A2A.md`: the measured agent-to-agent registry of the reference station (five identities, five peers, loopback
  ports, kind, enabled, today's liveness), the owner's rule that an agent does not initiate A2A without direct words,
  the reads that are allowed, the channel separation between session mail and A2A, and the measured root of the missing
  reflex: the harness has no identity in the registry, so it cannot be an addressee.
- `tools/dialect.py` implements the detection and the declaration check; `tests/test_dialects.py` enforces it on every
  fixture; `tests/test_public_docs.py` enforces English-only text, no machine-local paths and provenance on every claim.
- Every `.expect.json` now declares its `dialect`; markers for a deliberate violation are `dialect_violation`.
- `xml-doc` verdict (2026-10-22): the well-formedness contract of the dialect is now enforced where the dialect is
  decided, so a malformed XML document comes back as exit 1 with the parser's own message instead of a clean answer.
  Fixture `corpus/invalid/xml-malformed.xml`; the refusal and the well-formed control are pinned in
  `tests/test_dialects.py`, and a contradicted declaration still outranks well-formedness with exit 2.
- Corpus: `valid/phase-arbitrate.xtml` (a phase from the shipped set, accepted) beside `invalid/phase-from-data.xtml`
  (a phase outside it, exit 2) and `invalid/enum-scope-global.xtml` (an enum value outside the closed dictionary,
  exit 2) — the pair is the evidence that the closed set is closed and not merely broken. `invalid/dialect-*` and
  `examples/xml-doc-card.xml` cover the dialect rule.

## Proposed (not in 1.0)

- Dialect marker: optional root attribute `dialect="cxtml/1.0"`. The `delegation` profile already accepts extra root
  attributes; the `message` profile rejects unknown root attributes, so `dialect` would join its optional attributes.
- File extension: `.xtml` stays the only one. A document without escapes or cXTML profiles is plain XTML text, so the
  dialect marker, not the extension, is what tells the two apart.
- Remove the deprecated `argument name=` alias of `key=`.
