import json
from pathlib import Path
import tempfile
import threading
import unittest

from test_taskctl import SCRIPT, cmd


PLAN = """# Tasks
Source: approved artifact
Plan approval: approved

## T001: change {name}
- Depends on: none
- Touches: {name}.txt
- Goal: add {name}.txt
"""


class TwoSessionIntegrationTests(unittest.TestCase):
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

    def taskctl(self, *args, cwd):
        return json.loads(cmd("python3", str(SCRIPT), *args, cwd=cwd).stdout)

    def session(self, issue, owner, results):
        try:
            entry = self.taskctl("workspace", "get", "--issue", str(issue), cwd=self.root)
            worktree = Path(entry["worktree"])
            self.taskctl("workspace", "claim", "--issue", str(issue), "--owner", owner, cwd=self.root)
            plan = Path(entry["plan"])
            plan.parent.mkdir(parents=True)
            plan.write_text(PLAN.format(name=f"issue-{issue}"), encoding="utf-8")
            cmd("git", "add", str(plan), cwd=worktree)
            cmd("git", "commit", "-m", f"docs: plan {issue}", cwd=worktree)
            self.taskctl("init", "--plan", str(plan), "--base-branch", "main", cwd=worktree)
            self.taskctl("start", "--plan", str(plan), "--task", "T001", cwd=worktree)
            (worktree / f"issue-{issue}.txt").write_text("done\n", encoding="utf-8")
            cmd("git", "add", f"issue-{issue}.txt", cwd=worktree)
            cmd("git", "commit", "-m", f"feat: issue {issue}", cwd=worktree)
            head = cmd("git", "rev-parse", "HEAD", cwd=worktree).stdout.strip()
            receipt = worktree.parent.parent.parent / f"receipt-{issue}.json"
            receipt.write_text(json.dumps({
                "task_id": "T001", "commit_sha": head, "acceptance": "passed", "diff_review": "passed",
                "checks": [{"command": "test", "status": "passed"}], "limitations": [],
            }), encoding="utf-8")
            self.taskctl("complete", "--plan", str(plan), "--task", "T001", "--evidence", str(receipt), cwd=worktree)
            results[issue] = self.taskctl("status", "--plan", str(plan), cwd=worktree)
        except Exception as exc:  # surfaced by the main thread
            results[issue] = exc

    def test_two_sessions_run_independent_issues_concurrently(self):
        results = {}
        threads = [threading.Thread(target=self.session, args=(issue, f"session-{issue}", results))
                   for issue in (11, 12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        for issue in (11, 12):
            self.assertNotIsInstance(results[issue], Exception, results[issue])
            status = results[issue]
            self.assertEqual(status["branch"], f"fix/issue-{issue}")
            self.assertEqual(status["tasks"][0]["status"], "completed")
        self.assertNotEqual(results[11]["state_path"], results[12]["state_path"])
        self.assertEqual(cmd("git", "status", "--porcelain", cwd=self.root).stdout, "")
        self.assertEqual(cmd("git", "branch", "--show-current", cwd=self.root).stdout.strip(), "main")

        third = cmd("python3", str(SCRIPT), "workspace", "claim", "--issue", "11", "--owner", "intruder",
                    cwd=self.root, ok=False)
        self.assertIn("claimed by session-11", json.loads(third.stderr)["error"])

        plans = [str(self.root / ".worktrees" / f"issue-{issue}" / "docs" / "tasks" / f"issue-{issue}.md")
                 for issue in (11, 12)]
        self.assertEqual(self.taskctl("overlap", "--plans", *plans, cwd=self.root)["verdict"], "parallel")


if __name__ == "__main__":
    unittest.main()
