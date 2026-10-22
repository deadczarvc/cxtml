# Status of the published snapshot

`validator/` is the last publishable snapshot of the upstream reference validator, taken on 2026-10-22
and pinned by `SOURCE.lock`. It is **not** a byte-for-byte mirror of the current upstream.

`SOURCE.lock` therefore states three measured facts and nothing more:

- `mirror_sha256` — the sha256 of every file published here;
- `upstream_sha256` — the sha256 the upstream files had when this snapshot was measured;
- `map_sha256` — `null`: no substitution map exists, so the claim "map(upstream) equals the mirror" is
  not made.

| file | state measured on 2026-10-22 |
|---|---|
| `cmdcheck.py`, `codec.py`, `tests/test_codec.py` | identical to the upstream |
| `validate.py` | upstream code moved ahead (a state/learning block and a repair helper); 93236 B upstream vs 80167 B here |
| `vocab.py` | the upstream keeps its dictionary in data files; 40761 B upstream vs 45536 B here, with the constants still inline |
| `card-format.json` | the upstream added `level` to `routing_optional` |

For those three files logic identity does not hold: the difference is code, not prose. The substitution
map of `tools/sync_validator.py` may touch prose only, so no map can turn the current upstream into
these bytes. Copying upstream bytes in by hand is ruled out twice over: the mirror changes only through
the tool, and the upstream prose is private.

`python tools/sync_validator.py` checks the published bytes against `mirror_sha256`. The `--canon`,
`--update` and `--push` modes need the map and cannot run on this station; the drift above is measured
and reported, not repaired.
