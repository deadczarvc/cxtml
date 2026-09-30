# cXTML/1.0 rules (normative)

Keywords MUST, MUST NOT, SHOULD, MAY are used as in RFC 2119. Every rule carries its origin:
**[F]** = Kimi K3 technical report, arXiv 2607.24653, Appendix F (XTML chat template);
**[E]** = the reference encoder `encoding_k3.py` published with the Kimi K3 weights (function names cited, fetched 2026-10-01);
**[X]** = cXTML extension defined here.

### 1.1 Relationship to XTML

1. XTML is the markup of the Kimi K3 chat template [F]: XML with the angle brackets replaced by reserved special tokens. Moonshot AI defines it as a chat template, not as a standalone notation.
2. cXTML is a dialect of XTML for multi-agent prompts on any model [X]. Every document that is valid under App. F XTML (profile `kimi`) is a valid cXTML document.
3. cXTML adds exactly three things [X]: (a) a quoting rule for reserved markers inside text (1.6, 1.7); (b) the profiles `delegation` (with the routing v2 packet) and `message` (peer messages between agents); (c) the obligation to validate before delivery to any model that lacks the reserved tokens (1.10).

### 1.2 Two surface forms of the same markers

| marker | text form (paper notation, files, messages) | token form (K3 native) [E] |
|---|---|---|
| open | `[open]` | `<\|open\|>` control token (`OPEN_TOKEN`) |
| separator | `[sep]` | `<\|sep\|>` (`SEP_TOKEN`) |
| close | `[close]` | `<\|close\|>` (`CLOSE_TOKEN`) |
| end of message | `[end_of_msg]` | `<\|end_of_msg\|>` (`END_OF_MSG_TOKEN`) |

Bijection [X], built on [E]:

- text form -> token form: every marker spelling that is structure (not inside a literal region, 1.6) becomes the matching control token (`_control`, special tokens allowed); every other character run becomes text tokens (`_text`, special tokens not allowed). Attribute values are entity-decoded (1.7) and re-escaped the way `_escape_attr_value` does.
- token form -> text form: control tokens become their bracket spellings; text tokens are decoded; a decoded text run that contains a bracket spelling MUST be emitted inside a literal region (a code span whose backtick run is longer than any run inside it), so that it reads back as text.
- In token form, structure and quoted marker text are separated by the encoding channel (control vs text tokens), so no escaping exists or is needed there [E]. In text form the channel is gone, and 1.6 / 1.7 replace it.
- A token-form spelling such as `<|open|>` written in a text-form document is plain text, never a marker. An encoder MUST NOT emit it as a control token (the `_text` channel guarantees this) [E].

### 1.3 Elements

1. Open tag: open marker, element name, zero or more attributes, separator [F]: `[open]name key="value"[sep]`.
2. Close tag: close marker, element name, separator [F][E: `_close_tag` = control CLOSE + text name + control SEP]. The close name MUST equal the name of the innermost open element. A bare close marker without name and separator is INVALID; an earlier summary that described a bare close was a paraphrase error, not App. F.
3. Element names are ASCII: a letter, then letters, digits, `.`, `_`, `-` [X] (a Cyrillic letter that looks Latin would otherwise make two different tags look identical).
4. Attributes: `key="value"`, separated by whitespace, double quotes only, no key twice in one element [F layout, X uniqueness].
5. Content is everything between an open tag and its close tag: text, child elements, literal regions.

### 1.4 Documents

1. Exactly one root element. Markup after the root is closed is an error [X].
2. Only whitespace may follow the root, plus the end-of-message marker where the profile allows it (1.8) [X].
3. Text before the root is not part of the document; validators warn [X].
4. Nesting ceiling: profile `kimi` 4 levels, the depth of App. F Fig. 16 (`message` > `tools` > `call` > `argument`) [F]; profiles `delegation` and `message` 3 levels [X].
5. The root element MUST NOT contain an element with its own name [X].
6. In profiles `delegation` and `message` all text lives in sections: printable text directly in the root, between sections, is an error [X]. In profile `kimi` the message body is root text [F].

### 1.5 Balance

Every open tag has exactly one matching close tag, properly nested. An unclosed element, a close tag without an open one, a separator without a preceding open or close marker, and an open/close marker without its separator are errors [F structure, X diagnostics].

### 1.6 Reserved markers inside text: literal regions [X]

A reserved marker spelling is structure unless it lies inside a literal region. Literal regions exist only in element content, never in tags or attribute values.

1. Code span (CommonMark-derived): a maximal run of N backticks opens; the next maximal run of exactly N backticks closes. The closing run MUST occur before the next blank line (the span stays in its paragraph). A literal backtick inside the span is written by choosing a longer run (two backticks around text that contains one).
2. Fenced block: a line starting with at most three spaces and at least three backticks (the rest of that line holds no backtick) or at least three tildes opens; the first later line consisting of at most three spaces, the same character repeated at least as many times as the opening run, and optional trailing spaces closes. The region spans both fence lines.
3. An opener without its closer escapes nothing: the backticks or tildes are ordinary text and every marker after them counts as structure.
4. Recognition order is document order: at each point the earliest of {marker, literal-region opener} wins.
5. Validators SHOULD warn when a literal region contains a marker spelling: a stray pair of backticks in two sections of one paragraph can merge those sections silently.
6. Why not a backslash escape: text-form cards name Windows paths, and a path ending in a backslash directly before a close marker is common; backslash escaping would silently swallow that marker.
7. K3 native mode: an encoder MUST emit the content of a literal region as text tokens, never as control tokens.
8. Quotes [X]: a literal region that holds a reserved marker spelling is a quote. Its delimiters are not part of the text (a code span loses its backtick runs and, when its content starts and ends with a space, one pad space; a fenced block loses its two fence lines); a writer puts one pad space inside a code span whose text starts or ends with a backtick, and keeps the outer whitespace of the quoted paragraph outside the span. A literal region without a marker spelling is ordinary text and keeps its backticks. The text form may lack a faithful spelling for marker-free text whose backtick runs or fence lines would pair across element boundaries; the reference codec (`validator/codec.py`) refuses to write such a document in text form, while the token form always exists.

### 1.7 Attribute values

1. [E] `_escape_attr_value` writes `&` as `&amp;` and `"` as `&quot;`; no other escape and no unescape exist in the reference encoder.
2. [X] In text form a reserved marker MUST NOT appear raw in an attribute value (the separator would end the tag early; the others are the smuggling channel validators reject). To mention one, write its opening bracket as the numeric character reference `&#91;`: `id="quotes &#91;close] literally"`.
3. [X] Readers decode exactly `&#91;`, `&quot;`, `&amp;`, in that order; `&amp;` last, so `&amp;#91;` stays the literal text `&#91;`. Encoders escape `&` first, then `"`, then `[` where it begins a reserved spelling.
4. [X] Code spans are not literal regions inside attribute values.

### 1.8 End-of-message marker

1. [F] `[end_of_msg]` is the generation stop marker that follows a closed message.
2. [X] At most one, outside every element, and last in the document. Allowed in profiles `kimi` and `message`; forbidden in `delegation` (a delegation card that reached a K3-family stack would stop generation there).

### 1.9 Profiles

A profile fixes the element vocabulary and the extra checks; the lists are generated from the reference validator into part 3 and `profiles/*.json`, never kept by hand.

- `kimi` [F]: the original chat-template vocabulary; no mandatory sections. Validators return the advisory code 1 when clean, because this profile checks the original notation, not a cXTML card.
- `delegation` [X]: a task card for a delegate: mandatory core sections, the routing v2 JSON packet with strict fields and enums, optional canon-v2 sections with value vocabularies, an executable acceptance command, a report path that climbs nowhere.
- `message` [X, on F]: a peer message between agents. Root `message` with `role="peer"` [X] (the roles emitted by `encoding_k3.py` are system, user, tool, assistant; there is no `other`). A request MAY carry `call` elements with `tool` and `index` [E: `_render_assistant_segments`] and `argument` children with `key` and `type` [E]; `argument name=` is a deprecated alias of `key` and warns. A reply (ACK, NACK or HANDOFF with `re`) that answers a call carries the call's `tool` and `index` on the root, as an App. F tool result does [E: role `tool` message with `tool` and `index`]; the pair is both-or-neither and only on replies.

### 1.10 Validation before delivery [X]

A cXTML document addressed to a model without the reserved tokens MUST pass a conforming validator before delivery. Exit contract of the reference validator: 0 clean; 1 advisory (vocabulary complaint under `--strict`, or a clean result under the advisory profiles `kimi` / `any`); 2 structurally malformed, blocking.

### 1.11 Versioning

This is cXTML/1.0; changes are listed in CHANGELOG.md. A document-level dialect marker is a proposal, not part of 1.0 (see CHANGELOG.md, "Proposed").
