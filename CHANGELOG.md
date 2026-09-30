# Changelog

## cXTML/1.0 (unreleased, 2026-10-01)

- Rules and ABNF for the text form, each rule marked App. F, reference encoder, or cXTML extension.
- Two surface forms of the markers (bracket text form, K3 control tokens) and the bijection between them.
- Close tag = close marker + element name + separator; a bare close marker is invalid.
- Literal regions: CommonMark-style code spans and fenced blocks make reserved markers inside them text.
- Attribute values: `&amp;` and `&quot;` as in the reference encoder, plus `&#91;` for a quoted marker.
- Profiles `kimi`, `delegation` (routing v2), `message`; vocabulary generated from the reference validator.
- Conformance corpus with one expected verdict per card; valid cards include structure-preserving neutralizations of
  real delegation cards.
- Validator mirror pinned by `SOURCE.lock`; `validator/proposed/cxtml-1.0.patch` adds literal regions and the App. F
  nesting depth for profile `kimi`.

## Proposed (not in 1.0)

- Dialect marker: optional root attribute `dialect="cxtml/1.0"`. The `delegation` profile already accepts extra root
  attributes; the `message` profile rejects unknown root attributes, so `dialect` would join its optional attributes.
- File extension: `.xtml` stays the only one. A document without escapes or cXTML profiles is plain XTML text, so the
  dialect marker, not the extension, is what tells the two apart.
- Argument attributes: App. F Fig. 16 uses `key` / `type`; the `message` profile uses `name` / `type`. Accept `key`,
  then deprecate `name`.
