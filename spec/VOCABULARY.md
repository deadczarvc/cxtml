# Dynamic vocabulary: the dictionary as data

Status: **extension design, implemented in the reference implementation, not in this repository's mirror.**
The reference vocabulary module on the station is data-driven as of 2026-10-22; the module mirrored here
(`validator/vocab.py`) still carries constants. This document specifies the data-driven contract so the two can
converge deliberately, and so nobody adds a word by editing a constant again.

Provenance convention used in this document: **[F]** fact (directly observed or measured), **[I]** interpretation
or design decision of this arc, **[S]** partially supported (a statement that is true under stated conditions).
Grade: **A** primary source or a measurement made here, **B** source code or an official technical document,
**C** secondary report. Every claim below carries both; an unmarked claim is a defect, and `tests/test_public_docs.py`
refuses one.

## 1. Why the vocabulary moved out of code

1. The words of a profile used to live in four places at once: Python literals in the validator, prose blocks of
   `card-format.json`, and the vocabulary sections of two documentation files. They drifted apart, and a word could be
   accepted by one consumer and rejected by another. [F/A: reference module header, 2026-10-02/2026-10-22 history]
2. The station's rule that replaced it is "code as the readable source", which fixed the four-way drift but made every
   addition a code change with a release. The next step, taken on 2026-10-22, is the one specified here: the vocabulary
   is data, and code is the loader, the schema and the projection writer. [F/A: measured diff, station vs mirror]
3. Measured shape of that step: the data file is 43 893 bytes with 76 man articles and 4 profile introductions, the
   schema is 10 834 bytes, and the reference validator grew from 80 167 to 93 236 bytes while its vocabulary module
   moved from a 45 536-byte constants module to a 39 875-byte loader plus the data file. [F/A: file sizes and AST diff]

## 2. The data model

The vocabulary is one JSON object. Keys, as shipped by the reference implementation:

| key | shape | meaning |
|---|---|---|
| `schema` | string, exactly `xtml-vocab/1` | version of the vocabulary file itself |
| `about` | non-empty string | the same "this file is the source" statement, for a human reader |
| `profiles` | object | per profile: `delegation` has `core`, `optional`, `v2`, `tags`; `kimi`, `message`, `doc` have `tags` |
| `known_extra` | array of tags | tags that are a signal, not an error, when they appear outside the mandatory union |
| `enforced_count` | object tag → integer | sections whose repetition is an error, with the allowed count |
| `phases` | array, 5 values | routing phases: `collect`, `diagnose`, `implement`, `verify`, `arbitrate` |
| `tiers` | array, 4 values | escalation tiers: `luna`, `terra`, `sol`, `astra` |
| `loop_classes` | array, 3 values | `one-shot`, `continuable`, `ralph-round` |
| `capability_keys` | array, 5 values | capability keys of the requirement matrix |
| `matrix_flags` | array, 3 values | flags the preflight matrix checker accepts |
| `context_budget_keys` | array, 2 values | `max-input-tokens`, `report-inline-max` |
| `seed_policies` | array, 2 values | `none`, `context-inline` |
| `verdict_marker` | string | `VERDICT` |
| `routing_fields` | array, 12 values | required routing fields; `role` and `specialist` included |
| `routing_optional` | array | `requirements`, `level` |
| `routing_levels` | array, 2 values | `light`, `heavy` |
| `routing_enums` | object | closed dictionaries of `risk`, `scope`, `contract`, `failure` |
| `message` | object | root, role, attributes, types, sections and the call/argument contract of a peer message |
| `doc` | object | `roots` and `elements` of the document profile |
| `aliases` | object | field → spelling → `[canonical value, justification]` |
| `not_aliases` | object | field → spelling → reason, for spellings that must NOT be mapped |
| `intro` | array of pairs | profile → one-paragraph introduction rendered by `--man` |
| `articles` | array of objects | one man article per tag: `profile`, `tag`, `purpose`, `when`, `attrs`, `example` |

[F/A: keys read from the shipped data file; counts counted, not estimated]

## 3. Schema discipline

1. The schema is a JSON-Schema *subset*, and the loader enforces it on every import: `type`, `required`, `properties`,
   `additionalProperties`, `items`, `enum`, `pattern`, `minLength`, `minItems`, `maxItems`, `uniqueItems`, `minimum`,
   `maximum`. A keyword outside that list is not silently accepted. [F/B: schema header]
2. `additionalProperties: false` everywhere a closed object is described: a key that the schema does not name is an
   error, not room for the future. This is what makes "the vocabulary" a closed set rather than a habit. [F/B]
3. Tag names are `^[a-z][a-z0-9-]{0,39}$`; value names are `^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$`. Values are
   case-sensitive in the file and compared case-insensitively only where the alias loader normalises (`-` and `_`
   folded, lowercased). [F/B]
4. Duplicate JSON keys are refused, not silently collapsed: the loader constructs objects with a duplicate-key hook and
   raises, because "the last one wins" is exactly how a word disappears without anyone editing a line. [F/B]
5. A tag added to an `optional`, `v2` or `tags` list is allowed; a tag added to a *required* list is a contract change
   and is refused by the growth tool (section 7). [F/B]

## 4. Loader contract: where the file is, and what happens when it is missing

1. The data file is looked up next to the module, then at `<root>/config/xtml-vocab.json`, then at the canonical ops
   location. The order is named by `--where`, so "which vocabulary is in force" is a one-command answer. [F/B]
2. A pin via environment variable is authoritative, not a fallback: if the pinned file does not exist the loader raises
   and names the pin. Continuing to the next candidate would let a fixture believe it was checked against its own
   vocabulary while a foreign file was read. [F/B]
3. A missing data file is a loud failure that names every path it tried. There is no silent fallback to constants: the
   old behaviour hid the breakage behind a healthy-looking validator. [F/B]
4. The schema lives next to the data file it describes, with no second search order to drift. [F/B]

## 5. Projections: two generated views, never hand-edited

1. `card-format.json` is a **generated projection** for consumers that are not Python. It carries the routing contract,
   the phases and the dictionaries in a form a JSON consumer can read. [F/B]
2. The `PHASES = (...)` line inside the vocabulary module is also a **generated projection**, for consumers that read
   that source text with a regular expression instead of importing it. [F/B]
3. Both are written by one tool (`--write`) and checked by the same tool (`--check`); a hand edit is drift and the check
   exits non-zero. [F/B]
4. Editing a projection by hand is therefore forbidden by construction, not by etiquette. The repository mirrors this
   rule: its own projection is regenerated by `tools/render_spec.py`, and the profiles in `profiles/*.json` and part 3
   of `spec/SPEC.md` are generated from the validator. [F/A: `tools/render_spec.py --check` is a CI gate here]

## 6. Aliases: one canonical spelling per meaning

1. An alias maps a spelling that people actually write onto the canonical enum value, with a justification string next
   to it: `"medium": ["elevated", "the scale low < elevated < critical has one middle step"]`. [F/B: shape of `aliases`]
2. `not_aliases` names a spelling that must *not* be mapped, with the reason: `high` is refused because it fits both
   `elevated` and `critical` on that scale. A spelling that is both allowed and forbidden in the same field is an error,
   and so is a ban without a reason. [F/B: alias checker]
3. Two values that collide after normalisation are an error, and so is an alias pointing at a value that is not in the
   enum. The checker is pure: the suites feed it broken tables on purpose. [F/B]
4. Consequence for this repository: the routing enums are contract, and a card that writes `scope="global"` is refused
   here rather than quietly understood. See `corpus/invalid/enum-scope-global.xtml`. [F/A: validator exit 2]

## 7. Growing the vocabulary: one tool, three gates, a rollback, no deletion

1. Three operations exist: `add-tag`, `add-phase`, `add-enum-value`. Each takes `--why` (recorded) and exactly one of
   `--dry-run` (show the data diff and run gate 1, write nothing) or `--apply` (write, regenerate, run all gates).
   "Silent write" is not a mode. [F/B: growth tool CLI]
2. `--apply` makes a backup, writes the data file, regenerates **both** projections, syncs the intentional copies, then
   runs three gates: (1) schema plus the loader's own self-check, (2) the vocabulary-sync checker, (3) the five XTML
   suites. [F/B]
3. If any gate is red the tool restores the backup and regenerates the projections from the restored data, then exits 1.
   A vocabulary that is half-applied is not a state you can reach. [F/B]
4. Every apply is journalled append-only: who, what, when, why, both sha256 values, every gate exit code, and
   `applied` or `rolled_back`. The history cannot be rewritten by a later failure. [F/B]
5. Every apply must be a strict superset of the file it read: an edit disguised as an addition is refused. [F/B]
6. **Removal is not implemented by design.** Dropping a word is a human decision with its own review; automation may only
   add, and only through the gates. [F/B]
7. Refused additions, with the reason the tool gives: a tag into the mandatory core of `delegation` (it would become a
   new required section, and every historical card without it would start failing) and a tag into the `message` profile
   (all of its sections are mandatory, so a new one would make historical messages incomplete). [F/B]

## 8. What the validator does with the data

1. The validator reads the phases, tiers and routing enums from the vocabulary, so a value outside the shipped set is a
   structural error (exit 2), not a warning. Measured here: a card with `phase="research"` and a card with
   `scope="global"` are both refused with the offending value and the accepted list printed. [F/A]
2. The vocabulary module also carries the *learned replacement* table: a diagnostic value may be replaced from evidence
   accumulated across sessions, scored by a Wilson lower bound with a floor of 0.5, at least 2 sessions and 3 cards,
   over a 180-day horizon and a 1-hour pairing window, z = 1.645. Such a replacement is logged as automatic learning,
   never as a human lesson. [F/B: constants and docstring of the learned table]
3. A learned replacement cannot widen the enum: it substitutes one accepted value for another spelling of the same
   meaning, and the alias checker still has to accept the pair. [I/B]

## 9. Checklist for changing a word

1. Add it with the growth tool, never by hand: `--dry-run` first, read the data diff, then `--apply`. [F/B]
2. Read the journal entry afterwards: both hashes, three gate codes, result. [F/B]
3. Do not edit `card-format.json` or the `PHASES` line; regenerate them. [F/B]
4. If the word belongs to a required list, stop: that is an owner-level contract change, not an addition. [F/B]
5. Re-run this repository's gates (`tools/render_spec.py --check`, `tools/sanitize_scan.py`, `python -m pytest -q`) after
   any mirror sync, because the projection in part 3 of the spec is generated from the validator. [F/A]

## 10. Gaps recorded, not hidden

1. The mirror in this repository is not data-driven yet: `validator/vocab.py` here still carries constants, so a reader
   of this repository cannot see the data file. Closing that gap is a mirror sync, and the mirror changes only through
   `tools/sync_validator.py`. [F/A]
2. The substitution map that `sync_validator.py --canon/--update/--push` needs is not present on this station, so the
   mirror cannot be updated by its own tool; the drift is therefore measured and reported, not repaired. `SOURCE.lock`
   carries no map (`map_sha256: null`); it asserts the sha256 of the published bytes and the sha256 the upstream had on
   2026-10-22. Three files differ and the difference is code, so no prose map could reconcile them — `validator/SNAPSHOT.md`
   names each one. [F/A]
3. The station's data file is a private artefact with private prose; publishing it verbatim is not acceptable. What is
   publishable is the mechanism specified here, which is why this document describes shapes and rules rather than
   copying articles. [I/B]
