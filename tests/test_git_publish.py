from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.git_publish import (
    RemoteSyncError,
    is_non_fast_forward_error,
    order_months_from_csv,
    run_git,
    sync_remote_preserving,
)


class GitPublishTests(unittest.TestCase):
    def test_order_month_parser_returns_distinct_months(self) -> None:
        content = "Store,Date,ASIN\nA,2026-07-01,X\nA,2026-08-02,Y\nA,2026-08-03,Z\n"
        self.assertEqual(order_months_from_csv(content), {"2026-07", "2026-08"})

    def test_detects_fetch_first_error(self) -> None:
        error = subprocess.CalledProcessError(
            1,
            ["git", "push"],
            stderr="! [rejected] main -> main (fetch first)",
        )
        self.assertTrue(is_non_fast_forward_error(error))

    def test_sync_keeps_local_snapshot_and_merges_remote_code(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            remote = root / "remote.git"
            seed = root / "seed"
            local = root / "local"
            other = root / "other"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
            subprocess.run(["git", "clone", str(remote), str(seed)], check=True, capture_output=True)
            run_git(seed, "config", "user.email", "tests@example.com")
            run_git(seed, "config", "user.name", "Tests")
            (seed / "snapshot").mkdir()
            (seed / "snapshot" / "dashboard_snapshot.csv").write_text("base\n", encoding="utf-8")
            (seed / "app.py").write_text("base\n", encoding="utf-8")
            run_git(seed, "add", ".")
            run_git(seed, "commit", "-m", "base")
            run_git(seed, "branch", "-M", "main")
            run_git(seed, "push", "-u", "origin", "main")

            subprocess.run(
                ["git", "clone", "--branch", "main", str(remote), str(local)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "clone", "--branch", "main", str(remote), str(other)],
                check=True,
                capture_output=True,
            )
            for repo in (local, other):
                run_git(repo, "config", "user.email", "tests@example.com")
                run_git(repo, "config", "user.name", "Tests")

            (local / "snapshot" / "dashboard_snapshot.csv").write_text("local latest\n", encoding="utf-8")
            run_git(local, "add", ".")
            run_git(local, "commit", "-m", "local snapshot")

            (other / "snapshot" / "dashboard_snapshot.csv").write_text("remote snapshot\n", encoding="utf-8")
            (other / "app.py").write_text("remote code\n", encoding="utf-8")
            run_git(other, "add", ".")
            run_git(other, "commit", "-m", "remote update")
            run_git(other, "push", "origin", "main")

            sync_remote_preserving(local, ["snapshot/dashboard_snapshot.csv"])

            self.assertEqual(
                (local / "snapshot" / "dashboard_snapshot.csv").read_text(encoding="utf-8"),
                "local latest\n",
            )
            self.assertEqual((local / "app.py").read_text(encoding="utf-8"), "remote code\n")
            self.assertEqual(run_git(local, "status", "--porcelain").stdout, "")

    def test_sync_blocks_local_snapshot_that_drops_remote_months(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            remote = root / "remote.git"
            seed = root / "seed"
            local = root / "local"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
            subprocess.run(["git", "clone", str(remote), str(seed)], check=True, capture_output=True)
            run_git(seed, "config", "user.email", "tests@example.com")
            run_git(seed, "config", "user.name", "Tests")
            (seed / "snapshot").mkdir()
            (seed / "snapshot" / "dashboard_snapshot.csv").write_text(
                "Store,Date,ASIN\nA,2026-07-01,X\nA,2026-08-01,Y\n",
                encoding="utf-8",
            )
            run_git(seed, "add", ".")
            run_git(seed, "commit", "-m", "historical snapshot")
            run_git(seed, "branch", "-M", "main")
            run_git(seed, "push", "-u", "origin", "main")

            subprocess.run(
                ["git", "clone", "--branch", "main", str(remote), str(local)],
                check=True,
                capture_output=True,
            )
            run_git(local, "config", "user.email", "tests@example.com")
            run_git(local, "config", "user.name", "Tests")
            (local / "snapshot" / "dashboard_snapshot.csv").write_text(
                "Store,Date,ASIN\nA,2026-08-02,Z\n",
                encoding="utf-8",
            )
            run_git(local, "add", ".")
            run_git(local, "commit", "-m", "drops July")

            with self.assertRaisesRegex(RemoteSyncError, "2026-07"):
                sync_remote_preserving(
                    local, ["snapshot/dashboard_snapshot.csv"]
                )


if __name__ == "__main__":
    unittest.main()
