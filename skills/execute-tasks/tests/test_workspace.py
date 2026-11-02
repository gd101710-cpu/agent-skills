import fcntl
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_taskctl import SCRIPT, cmd


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        base = Path(self.temporary_directory.name)
        self.remote = base / "remote.git"
        self.root = base / "repo"
        cmd("git", "init", "--bare", "-b", "main", str(self.remote))
        cmd("git", "init", "-b", "main", str(self.root))
        cmd("git", "config", "user.name", "Test Agent", cwd=self.root)
        cmd("git", "config", "user.email", "agent@example.invalid", cwd=self.root)
        (self.root / "README.md").write_text("initial\n", encoding="utf-8")
        cmd("git", "add", "README.md", cwd=self.root)
        cmd("git", "commit", "-m", "chore: initial", cwd=self.root)
        cmd("git", "remote", "add", "origin", str(self.remote), cwd=self.root)
        cmd("git", "push", "-u", "origin", "main", cwd=self.root)
        cmd("git", "remote", "set-head", "origin", "main", cwd=self.root)

    def workspace(self, *args, cwd=None, ok=True):
        result = cmd("python3", str(SCRIPT), "workspace", *args, cwd=cwd or self.root, ok=ok)
        return json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def status(self, path):
        return cmd("git", "status", "--porcelain", cwd=path).stdout

    def test_get_creates_once_and_reuses_from_any_checkout(self):
        first = self.workspace("get", "--issue", "7")
        worktree = Path(first["worktree"])
        self.assertEqual(worktree, (self.root / ".worktrees" / "issue-7").resolve())
        self.assertEqual(first["branch"], "fix/issue-7")
        self.assertEqual(first["base"], "main")
        self.assertEqual(cmd("git", "branch", "--show-current", cwd=worktree).stdout.strip(), "fix/issue-7")
        self.assertEqual(self.workspace("get", "--issue", "7"), first)
        self.assertEqual(self.workspace("get", "--issue", "7", cwd=worktree), first)
        self.assertEqual(self.workspace("get", cwd=worktree), first)
        self.assertEqual(self.status(self.root), "")
        self.workspace("get", "--issue", "8")
        exclude = (self.root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(exclude.splitlines().count(".worktrees/"), 1)

    def test_get_without_issue_in_main_checkout_lists_candidates(self):
        self.workspace("get", "--issue", "7")
        error = self.workspace("get", ok=False)
        self.assertFalse(error["ok"])
        self.assertIn("#7", error["error"])

    def test_get_refuses_unregistered_branch_or_path(self):
        cmd("git", "branch", "fix/issue-9", cwd=self.root)
        error = self.workspace("get", "--issue", "9", ok=False)
        self.assertIn("Unregistered branch", error["error"])
        (self.root / ".worktrees" / "issue-10").mkdir(parents=True)
        error = self.workspace("get", "--issue", "10", ok=False)
        self.assertIn("Unregistered path", error["error"])
        self.assertEqual(self.workspace("list")["workspaces"], [])

    def test_get_fails_when_registered_worktree_is_missing(self):
        entry = self.workspace("get", "--issue", "7")
        cmd("git", "worktree", "remove", entry["worktree"], cwd=self.root)
        error = self.workspace("get", "--issue", "7", ok=False)
        self.assertIn("reconcile", error["error"])

    def test_list_reports_existence_and_dirty_state(self):
        entry = self.workspace("get", "--issue", "7")
        (Path(entry["worktree"]) / "new.txt").write_text("x\n", encoding="utf-8")
        listed = self.workspace("list")["workspaces"]
        self.assertEqual([(item["issue"], item["exists"], item["dirty"]) for item in listed], [(7, True, True)])

    def test_remove_refuses_dirty_and_unregistered(self):
        entry = self.workspace("get", "--issue", "7")
        worktree = Path(entry["worktree"])
        (worktree / "new.txt").write_text("x\n", encoding="utf-8")
        error = self.workspace("remove", "--issue", "7", ok=False)
        self.assertIn("uncommitted", error["error"])
        self.assertTrue(worktree.is_dir())
        (worktree / "new.txt").unlink()
        removed = self.workspace("remove", "--issue", "7")
        self.assertTrue(removed["removed"])
        self.assertFalse(worktree.exists())
        self.assertEqual(self.workspace("list")["workspaces"], [])
        error = self.workspace("remove", "--issue", "7", ok=False)
        self.assertIn("no registered workspace", error["error"])

    def test_remove_archives_the_worktree_ledger(self):
        entry = self.workspace("get", "--issue", "7")
        ledger = Path(cmd("git", "rev-parse", "--path-format=absolute", "--git-path",
                          "agent-workflow/progress.json", cwd=entry["worktree"]).stdout.strip())
        ledger.parent.mkdir(parents=True)
        ledger.write_text(json.dumps({"version": 2, "tasks": {}}), encoding="utf-8")
        removed = self.workspace("remove", "--issue", "7")
        archived = Path(removed["archived_ledger"])
        self.assertEqual(archived, self.root / ".git" / "agent-workflow" / "history" / "issue-7" / "progress.json")
        self.assertEqual(json.loads(archived.read_text(encoding="utf-8"))["version"], 2)

    def test_unregistered_worktree_is_never_touched(self):
        other = self.root.parent / "other"
        cmd("git", "worktree", "add", "-b", "other", str(other), cwd=self.root)
        error = self.workspace("get", cwd=other, ok=False)
        self.assertIn("not a registered issue workspace", error["error"])
        self.workspace("get", "--issue", "7")
        self.assertEqual([item["issue"] for item in self.workspace("list")["workspaces"]], [7])
        self.assertTrue(other.is_dir())

    def test_claim_and_release_lease(self):
        self.workspace("get", "--issue", "7")
        claimed = self.workspace("claim", "--issue", "7", "--owner", "a")
        self.assertEqual(claimed["lease"]["owner"], "a")
        self.assertEqual(self.workspace("claim", "--issue", "7", "--owner", "a")["lease"], claimed["lease"])
        error = self.workspace("claim", "--issue", "7", "--owner", "b", ok=False)
        self.assertIn("claimed by a", error["error"])
        error = self.workspace("release", "--issue", "7", "--owner", "b", ok=False)
        self.assertIn("claimed by a", error["error"])
        error = self.workspace("remove", "--issue", "7", ok=False)
        self.assertIn("release it first", error["error"])
        self.assertEqual(self.workspace("list")["workspaces"][0]["lease"]["owner"], "a")
        self.assertIsNone(self.workspace("release", "--issue", "7", "--owner", "a")["lease"])
        self.assertEqual(self.workspace("claim", "--issue", "7", "--owner", "b")["lease"]["owner"], "b")
        self.assertIsNone(self.workspace("release", "--issue", "7", "--owner", "a", "--force")["lease"])
        error = self.workspace("claim", "--issue", "99", "--owner", "a", ok=False)
        self.assertIn("workspace get", error["error"])

    def test_parallel_processes_keep_registry_consistent(self):
        def spawn(*args):
            return subprocess.Popen(["python3", str(SCRIPT), "workspace", *args], cwd=self.root,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        getters = [spawn("get", "--issue", str(issue)) for issue in range(1, 7)]
        for process in getters:
            process.communicate()
            self.assertEqual(process.returncode, 0)
        claimers = [spawn("claim", "--issue", "3", "--owner", f"owner-{index}") for index in range(6)]
        results = [process.communicate() and process.returncode for process in claimers]
        self.assertEqual(results.count(0), 1)
        listed = self.workspace("list")["workspaces"]
        self.assertEqual([item["issue"] for item in listed], [1, 2, 3, 4, 5, 6])
        self.assertTrue(listed[2]["lease"]["owner"].startswith("owner-"))
        self.assertEqual(len(cmd("git", "worktree", "list", cwd=self.root).stdout.splitlines()), 7)

    def test_lock_timeout_fails_without_partial_write(self):
        self.workspace("get", "--issue", "7")
        lock_path = self.root / ".git" / "agent-workflow" / "issues" / ".lock"
        with open(lock_path, "a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            error = self.workspace("claim", "--issue", "7", "--owner", "a", "--lock-timeout", "0.3", ok=False)
            fcntl.flock(handle, fcntl.LOCK_UN)
        self.assertIn("locked by another process", error["error"])
        self.assertIsNone(self.workspace("list")["workspaces"][0].get("lease"))

    def test_existing_ledger_commands_still_use_worktree_git_path(self):
        entry = self.workspace("get", "--issue", "7")
        worktree = Path(entry["worktree"])
        location = cmd("git", "rev-parse", "--git-path", "agent-workflow/progress.json", cwd=worktree).stdout
        self.assertIn("worktrees", location)


if __name__ == "__main__":
    unittest.main()
