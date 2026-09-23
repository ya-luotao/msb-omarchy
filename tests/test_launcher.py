import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from omarchy import Desktop, Error, download, lock


class LauncherTests(unittest.TestCase):
    def setUp(self):
        # Short, like a real state directory: the runtime's socket paths must fit in 104 bytes.
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.state = self.directory / "desktop state"
        binary = self.directory / "graphics runtime"
        shutil.copyfile(ROOT / "tests/fake_msb.py", binary)
        binary.chmod(0o755)
        firmware = self.directory / "firmware"
        firmware.touch()
        self.env = dict(os.environ, MSB=str(binary), MSB_HOME=str(self.state),
                        MSB_LIBKRUNFW_PATH=str(firmware),
                        SHARED_DIR=str(self.directory / "Shared files"), TAG="test:desktop")
        for name in ("FAKE_LIST_ERROR", "FAKE_NOT_READY", "PROFILE", "MSB_GPU_DISPLAY"):
            self.env.pop(name, None)

    def invoke(self, *args, success=True, **env):
        result = subprocess.run([sys.executable, str(ROOT / "lib/omarchy.py"), *args],
                                env=dict(self.env, **env), text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def calls(self, command=None):
        path = self.state / "calls.jsonl"
        calls = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [call for call in calls if command is None or call["args"][0] == command]

    def start(self, *args, **env):
        return self.invoke("run", "--no-display", *args, **env)

    def test_reopening_keeps_vm_disk_and_never_replaces(self):
        self.start()
        document = self.state / "guest-document"
        document.write_text("important edited document")
        self.start()
        self.assertEqual(document.read_text(), "important edited document")
        self.assertEqual(len(self.calls("run")), 1)
        self.assertFalse(self.calls("remove"))
        self.assertNotIn("--replace", self.calls("run")[0]["args"])

    def test_stopped_vm_resumes_saved_display_profile(self):
        self.start("--profile", "standard")
        self.invoke("stop")
        self.start(PROFILE="light", MSB_GPU_DISPLAY="800x600")
        self.assertEqual(self.calls("start")[0]["display"], "1920x1080")
        self.assertEqual(len(self.calls("run")), 1)

    def test_crashed_vm_resumes_without_replacing_disk(self):
        self.start("--profile", "standard")
        document = self.state / "guest-document"
        document.write_text("work from before the Mac restarted")
        state_path = self.state / "fake-state.json"
        state = json.loads(state_path.read_text())
        state["omarchy"]["status"] = "Crashed"
        state_path.write_text(json.dumps(state))
        result = self.start()
        self.assertIn("unclean shutdown", result.stderr)
        self.assertEqual(self.calls("start")[0]["display"], "1920x1080")
        self.assertEqual(document.read_text(), "work from before the Mac restarted")
        self.assertEqual(len(self.calls("run")), 1)
        self.assertFalse(self.calls("remove"))

    def test_paused_vm_resumes_with_its_applications(self):
        self.start()
        self.invoke("pause")
        result = self.start()
        self.assertIn("where it was paused", result.stderr)
        self.assertEqual(len(self.calls("resume")), 1)
        self.assertFalse(self.calls("start"))
        self.assertEqual(len(self.calls("run")), 1)

    def test_paused_vm_can_be_stopped_and_reset(self):
        self.start()
        self.invoke("pause")
        self.invoke("stop")
        self.start()
        self.invoke("pause")
        self.invoke("reset", "--yes")
        self.assertEqual(len(self.calls("remove")), 1)

    def test_only_a_running_vm_can_be_paused(self):
        self.start()
        self.invoke("stop")
        result = self.invoke("pause", success=False)
        self.assertIn("Only a running desktop", result.stderr)
        self.assertFalse(self.calls("pause"))

    def test_state_path_too_long_for_sockets_is_rejected_before_msb_runs(self):
        long_state = self.directory / ("x" * (60 - len(str(self.directory))))
        result = self.start(success=False, MSB_HOME=str(long_state))
        self.assertIn("too long", result.stderr)
        self.assertFalse(self.calls())

    def test_database_failure_does_not_create_or_remove(self):
        self.start(success=False, FAKE_LIST_ERROR="1")
        self.assertFalse(self.calls("run"))
        self.assertFalse(self.calls("remove"))

    def test_readiness_timeout_retains_vm_and_next_open_recovers(self):
        result = self.start("--timeout", "0.01", success=False, FAKE_NOT_READY="1")
        self.assertIn("VM is retained", result.stderr)
        self.assertTrue((self.state / "guest-document").exists())
        self.start()
        self.assertEqual(len(self.calls("run")), 1)

    def test_reset_requires_explicit_confirmation(self):
        self.start()
        self.invoke("reset", success=False)
        self.assertTrue((self.state / "guest-document").exists())
        self.assertFalse(self.calls("remove"))

    def test_reset_preserves_shared_files(self):
        self.start()
        shared_file = Path(self.env["SHARED_DIR"]) / "keep.txt"
        shared_file.write_text("host document")
        self.invoke("reset", "--yes")
        self.assertEqual(shared_file.read_text(), "host document")
        self.assertFalse((self.state / "guest-document").exists())
        self.assertEqual(len(self.calls("remove")), 1)

    def test_unmanaged_vm_is_never_adopted_or_reset(self):
        self.state.mkdir()
        (self.state / "fake-state.json").write_text(json.dumps(
            {"omarchy": {"name": "omarchy", "status": "Stopped", "image": "other"}}))
        self.start(success=False)
        self.invoke("reset", "--yes", success=False)
        self.assertFalse(self.calls("run"))
        self.assertFalse(self.calls("start"))
        self.assertFalse(self.calls("remove"))

    def test_changed_profile_requires_separate_vm(self):
        self.start()
        self.start("--profile", "standard", success=False)
        self.assertEqual(len(self.calls("run")), 1)
        self.assertFalse(self.calls("remove"))

    def test_mount_path_with_spaces_is_one_argument_and_owned_by_guest(self):
        self.start()
        args = self.calls("run")[0]["args"]
        self.assertEqual(args[args.index("-v") + 1],
                         f"{self.env['SHARED_DIR']}:/home/omarchy/Shared:uid=1000,gid=1000")

    def test_global_config_path_is_not_inherited(self):
        self.start(MSB_CONFIG_PATH="/wrong/global-config.json")
        self.assertEqual(self.calls("list")[0]["config"], str(self.state / "config.json"))

    def test_concurrent_open_cannot_create_a_second_vm(self):
        with patch.dict(os.environ, self.env):
            path = Desktop().metadata_path("omarchy").with_suffix(".lock")
        with lock(path):
            self.start(success=False)
        self.assertFalse(self.calls("run"))

    def make_database(self, rows):
        (self.state / "db").mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.state / "db/msb.db") as db:
            db.execute("create table sandbox (name text)")
            db.executemany("insert into sandbox values (?)", [(row,) for row in rows])

    def backups(self):
        return sorted((self.state / "db-backups").glob("*.db")) if (self.state / "db-backups").exists() else []

    def new_runtime(self):
        """A second installed runtime, as a pinned upgrade would add."""
        binary = self.directory / "newer runtime"
        shutil.copyfile(ROOT / "tests/fake_msb.py", binary)
        binary.chmod(0o755)
        return {"MSB": str(binary), "FAKE_VERSION": "msb 0.0.2"}

    def test_unrecorded_database_is_backed_up_before_first_use(self):
        self.make_database(["omarchy"])
        self.start()
        self.start()
        self.assertEqual(len(self.backups()), 1)
        self.assertIn("unknown", self.backups()[0].name)

    def test_runtime_change_backs_up_database_once(self):
        self.start()
        self.invoke("stop")
        self.make_database(["omarchy"])
        self.start(**self.new_runtime())
        self.start(**self.new_runtime())
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertIn("msb-0.0.1", backups[0].name)
        with sqlite3.connect(backups[0]) as db:
            self.assertEqual(db.execute("select name from sandbox").fetchall(), [("omarchy",)])

    def test_runtime_change_refuses_while_previous_runtime_has_active_vms(self):
        self.start()
        self.make_database(["omarchy"])
        result = self.start(success=False, **self.new_runtime())
        self.assertIn("still active", result.stderr)
        self.assertIn("bin/stop --name omarchy", result.stderr)
        self.assertEqual(self.backups(), [])
        self.invoke("stop")
        self.start(**self.new_runtime())
        self.assertEqual(len(self.backups()), 1)

    def test_failed_checksum_keeps_previously_downloaded_file(self):
        archive = self.directory / "download.tar.gz"
        archive.write_bytes(b"previous artifact")
        def corrupt_download(args, **kwargs):
            Path(args[args.index("--output") + 1]).write_bytes(b"corrupt download")
        with patch("omarchy.execute", corrupt_download):
            with self.assertRaisesRegex(Error, "Checksum mismatch"):
                download({"url": "https://example.invalid/archive", "sha256": "0" * 64}, archive)
        self.assertEqual(archive.read_bytes(), b"previous artifact")
        self.assertFalse(archive.with_suffix(".part").exists())


if __name__ == "__main__":
    unittest.main()
