# Plugin contract: the validator and the card generator as three tools

Status: **the three tools exist in the contour's reference plugin (`dsh-xtml`) and are measured from its source; this
repository does not ship a plugin.** What this document fixes is the contract a plugin must satisfy if it exposes this
repository's validator and generator to an agent, and why the schemas are as small as they are.

Provenance convention: **[F]** fact (observed or measured), **[I]** interpretation or design rule, **[S]** partially
supported. Grade: **A** primary source or a measurement made here, **B** source code or an official technical
document, **C** secondary report. Every numbered claim carries one; `tests/test_public_docs.py` refuses a document
whose claims are unmarked.

## 1. The three tools

| tool | parameters | what it does |
|---|---|---|
| `xtml_validate` | 4: `path`, `text`, `profile` (enum of the four card profiles), `strict` | validates a document, returns the exit code, the validator's output verbatim, the detected dialect, and parsed element/warning/error counts |
| `xtml_profiles` | 0 | returns the profile registry (names and tag dictionaries) and the routing phases, both read from their source of truth |
| `xtml_card` | 2 required: `spec_path`, `out_path` | generates a delegation card from a JSON specification and returns the generator's exit code with the generator's own validator verdict |

[F/A: tool names, parameter counts and return fields read from the reference plugin; the fourth profile set is
`delegation`, `kimi`, `message`, `doc`, and `any` is deliberately not offered because it hides profile mistakes]

## 2. Why the schemas are small

1. Every tool schema is materialised as JSON in the request that offers it. A schema is therefore a per-call cost, and a
   nested schema (`oneOf` trees, per-profile unions, long closed lists) spends that cost on every single call, not once.
   [I/B]
2. The boundary has a JSON node ceiling: a schema with a deep tree can be cut or refused at the boundary, and a tool
   offered with a truncated schema is worse than a tool not offered at all, because the caller cannot tell which
   parameters survived. Keeping each schema flat and shallow keeps it well under any ceiling and makes the parameter set
   readable in one look. [I/B]
3. Small schemas also buy refusals: with four flat parameters the plugin can reject an impossible call (both `path` and
   `text`, neither of them, a profile outside the registry) before starting a process, and say which rule was broken.
   A free-form schema would push those refusals into the validator, where a wrong input looks like a verdict. [F/B]
4. The enum is doing contract work: `profile` is an enum of exactly the four card profiles. There is no `any`, because a
   caller that can pass `any` learns nothing from the answer. [F/A]
5. `strict` is a boolean, not a level string: it maps to the validator's own flag, and a level vocabulary invented at the
   boundary would need its own tests. [I/B]

## 3. "A false OK is forbidden": the refusals

The rule is one line: `ok` may be true only when the engine actually ran and returned exit code 0. Everything else is a
refusal that names its cause. Measured refusals of the reference plugin:

| condition | what the caller gets |
|---|---|
| both `path` and `text` given | not run, reason: the two are mutually exclusive, give exactly one |
| neither given | not run, reason: `path` or `text` is required |
| `profile` outside the registry | not run, the accepted set printed |
| the text has no card marker and no angle tag | not run, `dialect: unknown`, reason: nothing to check, a silent OK is forbidden |
| input longer than the input ceiling (400 000 characters) | refused rather than truncated, so the check is never silently run on a prefix |
| interpreter, card validator, XML validator, vocabulary or generator missing | not run, `ok: false`, the missing path named as a field and in the reason |
| the process could not be started | not run, reason with the error code and the command name |
| profile registry command exits non-zero | `ok: false`, the exit code and the first diagnostic line returned |
| profile registry exits 0 but no profile was parsed | `ok: false`: "returned 0, but the registry format was not parsed" — a parser failure is not an empty registry |
| routing phases not found in the vocabulary source | `ok: false`, phases are not invented as a default |
| generator exits non-zero | `ok: false`, generator exit code and validator exit surfaced separately |

[F/B: every row is a branch of the reference plugin's implementation, not a policy statement]

## 4. Propagation, not reinterpretation

1. The validator's output is returned **verbatim** alongside the parsed fields. Parsed counts are a convenience; the
   verbatim text is the evidence. [F/B]
2. `ok` is exactly `exit code == 0`. Advisory results (exit 1) and structural failures (exit 2) are not folded into a
   boolean that a caller could mistake for success. [F/B]
3. The generator runs the validator itself and surfaces `validator_exit` as a separate field, and reports whether the
   output file actually exists afterwards, rather than trusting that a zero exit wrote something. [F/B]
4. Output is capped and the cap is reported (`truncated: true`), so a long diagnostic is never silently shortened into a
   clean-looking answer. [F/B]
5. The plugin holds no vocabulary of its own: the profile registry comes from the validator's `--man` index and the
   phases from the vocabulary source, and both sources are named in the result. A second copy in the plugin would drift,
   and drift in a registry is invisible until it rejects a legal card. [F/B]

## 5. Rules this repository expects of any plugin that wraps it

1. The engine's exit code is the verdict. A wrapper MUST NOT map exit 2 to "warning" or exit 1 to "ok". [F/A: this
   repository's own conformance test asserts the exit codes of 174 cards]
2. A missing engine MUST produce a refusal naming the path, never a degraded check. [F/B]
3. The dialect MUST come from the detection rule (`spec/DIALECTS.md`), and a declared dialect that contradicts it MUST
   be refused. The reference plugin implements the detection but not yet the declaration comparison. [F/A]
4. A generator MUST validate what it wrote and MUST report the validator's exit code separately from its own. [F/B]
5. A wrapper MUST NOT accept `any` as a profile alias: the point of a profile is that it can be wrong. [F/A]
6. Input above the ceiling MUST be refused rather than truncated. [F/B]
