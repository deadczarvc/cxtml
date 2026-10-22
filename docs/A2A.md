# A2A: what the station actually measured

Status: **experience record.** This document reports the agent-to-agent (A2A) setup of the reference station as it was
measured, the owner's rule about who may open a conversation, and the measured reason why the reflex to use A2A does
not exist. It is not a specification of the A2A protocol, and it deliberately contains no addresses beyond loopback
ports, no token values and no machine-local paths.

Provenance convention: **[F]** fact (observed or measured), **[I]** interpretation, **[S]** partially supported
(a recorded statement, true as recorded). Grade: **A** primary source or a measurement made here, **B** source code or
an official technical document, **C** secondary report. Every numbered claim carries one;
`tests/test_public_docs.py` refuses a document whose claims are unmarked.

## 1. The registry: five identities, five peers

Measured on 2026-10-22 with the registry's own read-only listing command (`a2areg list`, exit 0). The listing prints one
`identity` element per identity and one `peer` element per peer:

| peer | loopback port | kind | enabled | liveness probe 2026-10-22 |
|---|---|---|---|---|
| `claude-code` | 9941 | inbound | 1 | closed (connect timed out at 0.6 s) |
| `codex` | 9942 | inbound | 1 | closed (connect timed out at 0.6 s) |
| `opencode` | 9943 | inbound | 1 | closed (connect timed out at 0.6 s) |
| `hermes-a2apeer` | 9903 | hermes | 1 | open |
| `hermes-main` | 9902 | hermes | 1 | open |

[F/A: registry listing; [F/A] for the probe, which is a TCP connect with a 0.6 s timeout and no A2A message — "open"
means "a listener accepted a connection", not "the peer is healthy"]

1. The five identities are `claude-code`, `codex`, `hermes-a2apeer`, `hermes-main`, `opencode`. Each identity carries a
   *reference* to a token file; the token itself is not stored in the registry. [F/A]
2. Peers and identities are different lists: an identity is who may call, a peer is who may be called, and the two sets
   happen to have the same five names here. [F/A]
3. `kind` is part of the record (`inbound` for the three editors, `hermes` for the two Hermes peers), and `enabled="1"`
   on all five — enabling is an explicit field, not the absence of a flag. [F/A]
4. The liveness column is today's observation, not a property of the registry: a peer that is enabled can still be down,
   and three of the five were. [F/A]

## 2. The owner's rule: an agent does not initiate

1. **An agent does not initiate A2A communication.** Until the owner says, in direct words, "talk to peer X", A2A is not
   used for sending. There is no reflex and there should be none. [S/A: owner's rule, recorded 2026-10-20]
2. Allowed without the owner's word, because they read and do not act in anyone's name: listing peers
   (`a2a list`) and reading a peer's agent card (`a2a card get`). [S/A]
3. Forbidden without the owner's word: `a2a send`, because that is a **live turn of another agent**, not a message
   dropped into a queue. The tool's own constraint says the same thing. [S/A]
4. The two channels must not be mixed. Session-to-session mail inside the harness addresses a session id and stays
   inside the station; A2A addresses a peer over the network and starts someone else's execution. The cost of a mistake
   is asymmetric: a bad session message stays home, a bad A2A message leaves it. [S/A]
5. Therefore the default channel is session mail and teammates; A2A is used only on the owner's explicit word, with the
   peer named and the task named. [S/A]
6. A neighbouring rule of the same nature: do not act in another's name without permission — the same reasoning that
   makes a measured number wait for the owner's word before it is applied. [S/A]

## 3. The measured root of the missing reflex

This is the part worth publishing, because it replaces a plausible story with a measurement.

1. The registry was searched for the harness's own identity: the substrings `dsh`, `deepseek`, `lead` and `session` were
   checked against every identity and every peer, and all returned false. The harness is not in the registry at all.
   [F/A: measurement of 2026-10-20, re-checked against the 2026-10-22 listing]
2. Consequence: the harness has no address, no agent card and no inbound queue in the agent network. **An agent without
   an identity cannot be an addressee.** [I/A]
3. The three hypotheses that came before the measurement — discovery, policy, routing — were symptoms of that single
   structural fact, not three separate defects. Fixing discovery would not have given the harness an address. [I/A]
4. The owner said the same thing about the workaround in direct words: session mail was invented while there was no
   standard mechanism in the agent environment, not out of preference. [S/A: owner's words, recorded 2026-10-20]
5. The conclusion drawn on the station: a workaround is justified only while the standard mechanism is absent; once it
   exists, the workaround stops being the main path and stays as a deliberate reserve, never as the first choice. [I/A]
6. This is why "the model does not think of A2A" was the wrong diagnosis: the model was never in a position to be
   addressed, and no amount of prompting adds an address. [I/A]

## 4. What it would take to become a peer

The station wrote down five steps; they are reported here as a plan, not as an achievement:

1. Create an identity through the registry's own tool (the registry is never edited by hand). [F/A]
2. Put the token in a file and store only the path in the registry; the token is never printed and never committed.
   [F/A]
3. Write an agent card: name, version, the JSON-RPC A2A interface, and the harness's capabilities. [I/B]
4. Implement an inbound A2A handler as a plugin of the harness, not as a script beside it. [I/B]
5. Register the peer (url, kind, enabled) and only then demote session mail to the reserve path. [I/B]

Acceptance for that plan, as recorded: the harness appears in the peer listing as up, with its own card, and a
neighbouring harness session can accept and process a task over A2A without the file mailbox. [S/A]

## 5. Gaps recorded, not hidden

1. As of the measurement, no identity for this harness exists in the registry; §4 is a plan, not a status. [F/A]
2. The liveness column is a TCP connect. It proves a listener, not a working agent card, and it is not an A2A handshake;
   an "open" port can still answer wrongly. [F/A]
3. The registry is mutated only by its own tool; this record did not mutate it, and does not describe its file format,
   because that format belongs to that tool. [F/A]
4. No A2A message was sent while producing this document. The allowed reads were used; the forbidden call was not.
   [F/A]
5. The rule in §2 is a policy of one owner on one station. It is published as experience, not as a protocol requirement,
   and it should be re-decided, not inherited, by anyone else. [I/A]
