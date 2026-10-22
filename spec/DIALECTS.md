# Dialects: `xtml-card` and `xml-doc`

Status: **the two dialects are measured behaviour of the reference tooling; the declaration rule is this arc's
proposal, implemented in `tools/dialect.py` and enforced on the repository's own fixtures by
`tests/test_dialects.py`.** Nothing here claims a validator feature that the mirrored validator lacks.

Provenance convention: **[F]** fact (observed or measured), **[I]** interpretation or proposal, **[S]** partially
supported. Grade: **A** primary source or a measurement made here, **B** source code or an official technical
document, **C** secondary report. Every numbered claim carries one; `tests/test_public_docs.py` refuses a document
whose claims are unmarked.

## 1. Why two dialects

1. The contour speaks two markup families about the same tree. `xtml-card` is the token markup of cXTML: `[open]`,
   `[sep]`, `[close]`, `[end_of_msg]`, checked against a profile vocabulary. `xml-doc` is ordinary XML with angle
   tags, checked for well-formedness only. [F/A: the reference plugin decides between them per document]
2. They are not two spellings of one contract. A profile fixes a closed vocabulary and extra checks; XML accepts any
   tag a schema or a reader is willing to see. Treating one as the other is how a document gets a verdict it did not
   earn. [I/A]
3. cXTML itself is a dialect of XTML in the sense of §1.1 of the rules; `xml-doc` is a second, coarser dialect in the
   same tooling, not a third version of cXTML. [F/A: rules §1.1 and the plugin's two engines]

## 2. Surface forms

| | `xtml-card` | `xml-doc` |
|---|---|---|
| structure | `[open]name k="v"[sep]…[close]name[sep]` | `<name k="v">…</name>` |
| stop marker | `[end_of_msg]` where the profile allows it | none |
| checked by | the card validator with a profile (`delegation`, `kimi`, `message`, `doc`) | a well-formedness validator with the `generic` profile |
| vocabulary | closed per profile; a tag outside it is a warning, an error under `--strict`, and an error for the closed `doc` profile | not checked |
| failure surface | exit 0 clean, 1 advisory, 2 structurally malformed | exit 0 well formed, 1 malformed, checked by `tools/dialect.py` |
| what it cannot express | arbitrary XML documents, namespaces, XML comments and processing instructions as such | the profile contract, routing, mandatory sections |

[F/A: measured engines, profiles and exit codes; the last row is [I/A] by construction]

## 3. Detection: the first structural token decides

1. The dialect is decided by the **first structural token in document order**, never by the file extension or the file
   name. Card markers are `[open]`, `[sep]`, `[close]`, `[end_of_msg]`; an angle tag is `</?name` where the name starts
   with a letter and continues with letters, digits, `.`, `_`, `:` or `-`. [F/B: reference plugin, `detectDialect`]
2. The decision reports its basis — the offset of the first card marker, the offset of the first angle tag, which rule
   decided, and the first structural token — so a wrong verdict can be argued with instead of guessed at. [F/B]
3. Offsets, not counts: `card_marker_at` and `angle_tag_at` are character offsets into the text, `null` when that token
   family is absent. [F/B]
4. Neither token family present means `unknown`. That is a refusal, not a pass: "there is nothing to check" must not be
   reported as "everything is fine". [F/A: measured refusal message of the card validator on a marker-free text]
5. Knowing the limit of this rule is part of using it: detection reads raw text, so a marker spelling quoted inside a
   code span still counts as a structural token. A document that quotes `[open]` before its first angle tag is
   detected as a card even if the author meant XML. Recorded as a gap in §6. [F/B]

## 4. The declaration rule

1. Every document handed to a checker MUST have an **out-of-band dialect declaration**, and the checker MUST compare
   that declaration with the detection of §3. [I/A]
2. A declaration that contradicts detection is a refusal with both values printed: the detected dialect, the token that
   decided it, and its offset. A declaration of `xml-doc` on a card, or `xtml-card` on an XML document, is not
   "either interpretation works". [I/A: implemented in `tools/dialect.py::declaration_complaints`]
3. An undetermined dialect is refused for the same reason, whether or not a declaration was supplied. [I/A]
4. Why out-of-band and not an attribute on the root: §1.11 of the rules already records that a document-level dialect
   marker is a proposal, not part of cXTML/1.0, and an attribute invented here would be checked by nobody. The
   declaration therefore lives where a consumer reads it: the caller's contract, and the repository's `.expect.json`
   fixtures. [F/A: rules §1.11; [I/A] for the fixture choice]
5. In this repository the declaration is a `dialect` field of every `.expect.json` next to a card, and
   `tests/test_dialects.py` fails when it is missing, unknown, or contradicted by the document. [F/A: the test is the
   enforcement, not this paragraph]

## 5. Refusals that prevent a false OK

| input | engine that would run | verdict |
|---|---|---|
| a card with `[open]…[close]` but a phase outside the shipped vocabulary | card validator, `delegation` | exit 2, the offending value and the accepted list printed |
| plain prose with no markers and no tags | none | refused: dialect undetermined, "silent OK is forbidden" |
| an XML document declared `xtml-card` | card validator, `delegation` | exit 2, "no XTML element in the document"; and the declaration check also refuses the mismatch |
| an XML document with `[open]` quoted before its first tag | card validator (by §3.5) | exit 2: the quote is read as structure, which is why the declaration is mandatory |
| a malformed XML document declared `xml-doc` | the well-formedness gate in `tools/dialect.py` | exit 1, `well_formed: false` and the parser's own message; a clean `xml-doc` verdict is not reachable |

[F/A: the first three rows were measured with the mirrored validator and `tools/dialect.py`; the fourth follows from
the detection rule and is recorded as a gap, not as a tested behaviour; the fifth was measured on
`corpus/invalid/xml-malformed.xml` (exit 1) against the well-formed control `examples/xml-doc-card.xml` (exit 0)]

## 6. Gaps recorded, not hidden

1. Detection is quote-blind (§3.5): a marker inside a literal region counts as a structural token. Closing this needs a
   detection pass that shares the validator's literal-region scanner; today it does not exist in either engine. [F/B]
2. The mirrored validator implements the card dialect only. `xml-doc` is checked for well-formedness by the standard
   library parser in `tools/dialect.py`, which is exactly the contract of that dialect (§2): a refusal with exit 1 on a
   malformed document, never a clean verdict. A schema, a namespace or a content model is not checked, because the
   dialect does not promise one and inventing it here would be a second, unowned contract. [F/A: measured on
   `corpus/invalid/xml-malformed.xml` and `examples/xml-doc-card.xml`]
3. The declaration rule is enforced on the repository's fixtures, not by the contour's plugin, which still infers the
   dialect instead of comparing a declaration. That is a gap in the plugin, stated here so a reader does not assume
   otherwise. [F/A]
4. No schema or vocabulary for `xml-doc` exists: the dialect is "well-formed XML", and any stronger promise would be
   invented. [I/A]
