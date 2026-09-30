#!/usr/bin/env python3
"""Keep validator/ an exact, provable mirror of the upstream reference validator.

    python tools/sync_validator.py                                   # mirror vs SOURCE.lock (CI)
    python tools/sync_validator.py --canon DIR --map FILE            # + drift vs upstream, logic identity
    python tools/sync_validator.py --canon DIR --map FILE --update   # resync mirror + lock, then check

The upstream validator is maintained outside this repository. Its comments and docstrings name
machine-local paths, so the mirror is the upstream bytes after a private, deterministic
substitution map (kept outside the repository). What is proven, not assumed:

  1. mirror bytes == sha256 in validator/SOURCE.lock            (always; catches local edits)
  2. upstream bytes == sha256 in SOURCE.lock                    (--canon; catches upstream drift)
  3. map(upstream) == mirror, byte for byte                     (--canon)
  4. logic identity: Python AST with docstrings removed is equal; JSON is equal once the
     human-only keys "why" and "notes" are dropped             (--canon; the map may touch prose only)

exit 0 in sync · 1 drift or mismatch (the reason is printed)
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIRROR = ROOT / "validator"
LOCK = MIRROR / "SOURCE.lock"
# upstream layout (relative to --canon): the reference validator lives in an ops tree
UPSTREAM = {
    "validate.py": "tools/xtml/validate.py",
    "cmdcheck.py": "tools/cmdcheck.py",
    "card-format.json": "config/card-format.json",
}
PROSE_KEYS = {"why", "notes"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sanitize(name: str, data: bytes, rules: dict) -> bytes:
    text = data.decode("utf-8")
    for old, new in rules.get(name, []):
        text = text.replace(old, new)
    return text.encode("utf-8")


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return tree


def _drop_prose(obj):
    if isinstance(obj, dict):
        return {k: _drop_prose(v) for k, v in obj.items() if k not in PROSE_KEYS}
    if isinstance(obj, list):
        return [_drop_prose(v) for v in obj]
    return obj


def logic_view(name: str, data: bytes) -> str:
    text = data.decode("utf-8")
    if name.endswith(".py"):
        return ast.dump(_strip_docstrings(ast.parse(text)))
    return json.dumps(_drop_prose(json.loads(text)), sort_keys=True, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--canon", type=Path, help="root of the upstream ops tree")
    ap.add_argument("--map", type=Path, help="private substitution map (JSON), outside the repo")
    ap.add_argument("--update", action="store_true", help="rewrite mirror + lock from upstream")
    a = ap.parse_args(argv)
    if (a.canon is None) != (a.map is None) or (a.update and a.canon is None):
        ap.error("--canon and --map go together; --update needs both")

    bad: list[str] = []
    if a.canon:
        rules = json.loads(a.map.read_text(encoding="utf-8"))
        up = {n: (a.canon / p).read_bytes() for n, p in UPSTREAM.items()}
        if a.update:
            for n, b in up.items():
                (MIRROR / n).write_bytes(sanitize(n, b, rules))
            LOCK.write_text(
                json.dumps(
                    {
                        "upstream_sha256": {n: sha(b) for n, b in up.items()},
                        "mirror_sha256": {n: sha((MIRROR / n).read_bytes()) for n in UPSTREAM},
                        "map_sha256": sha(a.map.read_bytes()),
                    },
                    indent=1,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        for n, b in up.items():
            if sha(b) != lock["upstream_sha256"][n]:
                bad.append(f"DRIFT {n}: upstream changed since the last sync — rerun with --update")
            mirror = (MIRROR / n).read_bytes()
            if sanitize(n, b, rules) != mirror:
                bad.append(f"MISMATCH {n}: map(upstream) differs from the mirror")
            if logic_view(n, b) != logic_view(n, sanitize(n, b, rules)):
                bad.append(f"LOGIC {n}: the substitution map touched code, not only prose")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for n in UPSTREAM:
        if sha((MIRROR / n).read_bytes()) != lock["mirror_sha256"][n]:
            bad.append(f"EDITED {n}: mirror bytes differ from SOURCE.lock — never edit the mirror by hand")

    for line in bad:
        print(line, file=sys.stderr)
    print("validator mirror: " + ("FAIL" if bad else "in sync") + (" (upstream checked)" if a.canon else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
