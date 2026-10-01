"""tools/sync_validator.py --push (W73): writes only when every precondition holds, backs up what it replaces."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOL = Path(__file__).resolve().parent.parent / "tools" / "sync_validator.py"
spec = importlib.util.spec_from_file_location("sync_validator_under_test", TOOL)
SV = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SV)


class Push(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mirror, self.canon, self.copies = self.tmp / "validator", self.tmp / "canon", self.tmp / "skill"
        for d in (self.mirror, self.canon / "t", self.copies):
            d.mkdir(parents=True)
        (self.canon / "t" / "v.py").write_bytes(b"OLD = 1\n")
        (self.copies / "v.py").write_bytes(b"OLD = 1\n")
        (self.mirror / "v.py").write_bytes(b"NEW = 2\n")
        self.map = self.tmp / "map.json"
        self.map.write_text(json.dumps({"v.py": [["private-name", "public"]]}), encoding="utf-8")
        lock = {"upstream_sha256": {"v.py": SV.sha(b"OLD = 1\n")}, "mirror_sha256": {"v.py": "x"}, "map_sha256": "x"}
        (self.mirror / "SOURCE.lock").write_text(json.dumps(lock), encoding="utf-8")
        for name, value in (
            ("MIRROR", self.mirror),
            ("LOCK", self.mirror / "SOURCE.lock"),
            ("UPSTREAM", {"v.py": "t/v.py"}),
            ("MIRROR_AT", {}),
        ):
            patcher = mock.patch.object(SV, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_push(self) -> int:
        argv = ["--canon", str(self.canon), "--map", str(self.map), "--push", "--backup-suffix", ".bak-t"]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return SV.main([*argv, "--also", str(self.copies)])

    def untouched(self) -> None:
        self.assertEqual((self.canon / "t" / "v.py").read_bytes(), b"OLD = 1\n")
        self.assertFalse((self.canon / "t" / "v.py.bak-t").exists())

    def test_clean_push_writes_upstream_and_copies_with_backups_then_checks_in_sync(self) -> None:
        self.assertEqual(self.run_push(), 0)
        for f in (self.canon / "t" / "v.py", self.copies / "v.py"):
            self.assertEqual(f.read_bytes(), b"NEW = 2\n")
            self.assertEqual(f.with_name("v.py.bak-t").read_bytes(), b"OLD = 1\n")
        self.assertEqual(json.loads(SV.LOCK.read_text())["upstream_sha256"]["v.py"], SV.sha(b"NEW = 2\n"))

    def test_drifted_upstream_is_refused(self) -> None:
        (self.canon / "t" / "v.py").write_bytes(b"SOMEONE = 3\n")
        self.assertEqual(self.run_push(), 1)
        self.assertEqual((self.canon / "t" / "v.py").read_bytes(), b"SOMEONE = 3\n")

    def test_diverged_copy_is_refused(self) -> None:
        (self.copies / "v.py").write_bytes(b"LOCAL = 4\n")
        self.assertEqual(self.run_push(), 1)
        self.untouched()

    def test_mirror_the_map_would_rewrite_is_refused(self) -> None:
        (self.mirror / "v.py").write_bytes(b"NAME = 'private-name'\n")
        self.assertEqual(self.run_push(), 1)
        self.untouched()


if __name__ == "__main__":
    unittest.main()
