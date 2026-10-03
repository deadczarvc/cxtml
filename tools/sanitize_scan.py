#!/usr/bin/env python3
"""Sanitization gate: nothing machine-local or personal in the repository.

    python tools/sanitize_scan.py                        # generic patterns (CI)
    python tools/sanitize_scan.py --deny-file FILE       # + private literal terms kept outside the repo

exit 0 = 0 hits · 1 = hits (each printed as path:line: kind)

Generic patterns live here. Names, hostnames and internal project names are private by nature, so
their list is passed in from outside the repository and never committed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    "windows-abs-path": r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]{1,2}[A-Za-z0-9_.~$-]",
    "posix-home": r"/(?:home|Users)/[^/\s]+",
    "cyrillic-home": r"Users[\\/]+[Ѐ-ӿ]",
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[A-Za-z]{2,}",
    "secret": r"sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
    r"|xox[abpr]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY|Bearer\s+[A-Za-z0-9._~+/-]{20,}",
    "private-ip": r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
    "intranet-host": r"\b[A-Za-z0-9-]+\.(?:local|lan|internal|corp|home\.arpa)\b",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="sanitization gate")
    ap.add_argument("--deny-file", type=Path, help="private literal terms, one per line (case-insensitive)")
    a = ap.parse_args(argv)
    rules = [(k, re.compile(p)) for k, p in PATTERNS.items()]
    if a.deny_file:
        terms = [t.strip() for t in a.deny_file.read_text(encoding="utf-8").splitlines() if t.strip()]
        rules += [("private-term", re.compile(re.escape(t), re.IGNORECASE)) for t in terms]
    # exactly what a commit would carry: tracked + untracked-not-ignored (caches and .git never count)
    listed = (
        subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True, check=True
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    files = [ROOT / p for p in listed if p and (ROOT / p).is_file()]
    hits = 0
    for path in sorted(files):
        text = path.read_text(encoding="utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            for kind, rx in rules:
                if rx.search(line):
                    hits += 1
                    print(f"{path.relative_to(ROOT).as_posix()}:{n}: {kind}")
    print(f"sanitization: {hits} hits in {len(files)} files" + (" (+ private deny list)" if a.deny_file else ""))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
