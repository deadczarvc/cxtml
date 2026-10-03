#!/usr/bin/env python3
"""Keep validator/ an exact, provable mirror of the upstream reference validator.

    python tools/sync_validator.py                                   # mirror vs SOURCE.lock (CI)
    python tools/sync_validator.py --canon DIR --map FILE            # + drift vs upstream, logic identity
    python tools/sync_validator.py --canon DIR --map FILE --update   # resync mirror + lock, then check
    python tools/sync_validator.py --canon DIR --map FILE --push --backup-suffix .bak-X [--also DIR ...]
                                                                     # repo -> upstream (+ flat copies), then check

The upstream validator is maintained outside this repository. Its comments and docstrings name
machine-local paths, so the mirror is the upstream bytes after a private, deterministic
substitution map (kept outside the repository). What is proven, not assumed:

  1. mirror bytes == sha256 in validator/SOURCE.lock            (always; catches local edits)
  2. upstream bytes == sha256 in SOURCE.lock                    (--canon; catches upstream drift)
  3. map(upstream) == mirror, byte for byte                     (--canon)
  4. logic identity: Python AST with docstrings removed is equal; JSON is equal once the
     human-only keys "why" and "notes" are dropped             (--canon; the map may touch prose only)

--push (W73 2026-10-01) is the other direction, for a change made and tested in this repository: it writes each
changed mirror file over its upstream file and over the same-named file in every --also directory (flat copies such as
a skill's scripts/), after a backup <file><suffix> of every file it replaces, then rewrites the lock and runs the full
check. It refuses, writing nothing, when the map would rewrite a mirror file (upstream would not be a plain copy), when
an upstream file drifted since the last sync (lock sha; a file new to the lock is compared with the mirror at git HEAD),
or when a copy differs from its upstream file (someone else's change).

exit 0 in sync · 1 drift or mismatch (the reason is printed)
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
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
    "codec.py": "tools/xtml/codec.py",
    "test_codec.py": "tools/xtml/tests/test_codec.py",  # W73: the codec's tests travel with it
    "vocab.py": "tools/xtml/vocab.py",  # R11: validate.py imports the vocabulary module
}
MIRROR_AT = {"test_codec.py": ROOT / "tests" / "test_codec.py"}  # default: MIRROR / name
PROSE_KEYS = {"why", "notes"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def mpath(name: str) -> Path:
    return MIRROR_AT.get(name, MIRROR / name)


def _head(path: Path) -> bytes:
    rel = path.relative_to(ROOT).as_posix()
    return subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{rel}"], capture_output=True, check=True).stdout


def push(canon: Path, rules: dict, also: list[Path], suffix: str) -> list[str]:
    """Mirror -> upstream (+ flat copies). Returns refusals; writes nothing unless there are none."""
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    bad, plan = [], []
    for n, rel in UPSTREAM.items():
        new, target = mpath(n).read_bytes(), canon / rel
        if sanitize(n, new, rules) != new:
            bad.append(f"PUSH {n}: the map rewrites the mirror, so upstream is not a plain copy of it")
            continue
        old = target.read_bytes()
        base = lock["upstream_sha256"].get(n) or sha(_head(mpath(n)))
        if sha(old) != base:
            bad.append(f"PUSH {n}: upstream drifted since the last sync — run --update and merge first")
            continue
        if old != new:
            plan.append((target, old, new))
        for d in also:
            c = d / n
            if c.is_file() and c.read_bytes() != new:
                if c.read_bytes() != old:
                    bad.append(f"PUSH {n}: copy {c} differs from its upstream file")
                plan.append((c, c.read_bytes(), new))
    if bad:
        return bad
    for path, old, new in plan:
        bak = path.with_name(path.name + suffix)
        if not bak.exists():
            bak.write_bytes(old)
        path.write_bytes(new)
        print(f"pushed {path} (backup {bak.name})")
    return []


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
    ap.add_argument("--push", action="store_true", help="write the mirror over upstream (+ --also copies), then lock")
    ap.add_argument("--also", type=Path, action="append", default=[], help="directory of flat copies (with --push)")
    ap.add_argument("--backup-suffix", help="backup suffix for every file --push replaces (required with --push)")
    a = ap.parse_args(argv)
    if (a.canon is None) != (a.map is None) or ((a.update or a.push) and a.canon is None):
        ap.error("--canon and --map go together; --update / --push need both")
    if a.push and (a.update or not a.backup_suffix):
        ap.error("--push needs --backup-suffix and excludes --update")

    bad: list[str] = []
    if a.canon:
        rules = json.loads(a.map.read_text(encoding="utf-8"))
        if a.push:
            refused = push(a.canon, rules, a.also, a.backup_suffix)
            for line in refused:
                print(line, file=sys.stderr)
            if refused:
                print("validator mirror: push refused, nothing written")
                return 1
        up = {n: (a.canon / p).read_bytes() for n, p in UPSTREAM.items()}
        if a.update:
            for n, b in up.items():
                mpath(n).write_bytes(sanitize(n, b, rules))
        if a.update or a.push:
            LOCK.write_text(
                json.dumps(
                    {
                        "upstream_sha256": {n: sha(b) for n, b in up.items()},
                        "mirror_sha256": {n: sha(mpath(n).read_bytes()) for n in UPSTREAM},
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
            if sha(b) != lock["upstream_sha256"].get(n):
                bad.append(f"DRIFT {n}: upstream changed since the last sync — rerun with --update")
            mirror = mpath(n).read_bytes()
            if sanitize(n, b, rules) != mirror:
                bad.append(f"MISMATCH {n}: map(upstream) differs from the mirror")
            if logic_view(n, b) != logic_view(n, sanitize(n, b, rules)):
                bad.append(f"LOGIC {n}: the substitution map touched code, not only prose")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for n in UPSTREAM:
        if sha(mpath(n).read_bytes()) != lock["mirror_sha256"].get(n):
            bad.append(f"EDITED {n}: mirror bytes differ from SOURCE.lock — never edit the mirror by hand")

    for line in bad:
        print(line, file=sys.stderr)
    print("validator mirror: " + ("FAIL" if bad else "in sync") + (" (upstream checked)" if a.canon else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
