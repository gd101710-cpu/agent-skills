import json
from pathlib import Path
import tempfile
import unittest

from test_taskctl import SCRIPT, cmd


class SessionFlowTests(unittest.TestCase):
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

    def taskctl(self, *args, ok=True):
        result = cmd("python3", str(SCRIPT), *args, cwd=self.root, ok=ok)
        return json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def complete(self, issue, *stages):
        for stage in stages:
            self.taskctl("workspace", "stage", "--issue", str(issue), "--complete", stage)

    def claim(self, issue, owner, ok=True):
        return self.taskctl("workspace", "claim", "--issue", str(issue), "--owner", owner, ok=ok)

    def test_two_sessions_each_drive_one_issue(self):
        sessions = {21: "claude:host:1", 22: "codex:host:2"}
        for issue, owner in sessions.items():
            self.taskctl("workspace", "get", "--issue", str(issue))
            self.claim(issue, owner)
            self.complete(issue, "precheck", "plan")
            self.taskctl("workspace", "state", "--issue", str(issue), "--set", "running")
        self.assertIn("claimed by codex:host:2", self.claim(22, "claude:host:1", ok=False)["error"])

        self.complete(21, "execute")
        self.taskctl("workspace", "state", "--issue", "21", "--set", "done")
        self.taskctl("workspace", "release", "--issue", "21", "--owner", sessions[21])
        self.taskctl("workspace", "state", "--issue", "22", "--set", "interrupted", "--reason", "usage limit")
        self.taskctl("workspace", "release", "--issue", "22", "--owner", "claude:host:3", "--force")
        self.claim(22, "claude:host:3")
        self.assertEqual(self.taskctl("pipeline", "show", "--issue", "22")["next_stage"], "execute")

        self.taskctl("workspace", "stage", "--issue", "22", "--insert", "write-ste", "--after", "execute",
                     "--id", "polish")
        pipeline = self.taskctl("pipeline", "show")["stages"]
        review = {"id": "review", "skill": "write-ste", "access": "read"}
        lint = {"id": "lint", "skill": "write-ste", "access": "read"}
        path = self.root / ".agent-workflow" / "pipeline.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"stages": [pipeline[0], lint, *pipeline[1:3], review, *pipeline[3:]]}),
                        encoding="utf-8")
        self.assertEqual(self.taskctl("pipeline", "validate")["stage_count"], 7)

        first = self.taskctl("pipeline", "show", "--issue", "21")
        self.assertEqual((first["skipped_new"], first["next_stage"]), (["lint"], "review"))
        self.complete(22, "execute")
        second = self.taskctl("pipeline", "show", "--issue", "22")
        self.assertEqual([stage["id"] for stage in second["stages"]][3:6], ["execute", "polish", "review"])
        self.assertEqual(second["next_stage"], "polish")
        self.complete(22, "polish", "review", "pr")
        self.assertEqual(self.taskctl("pipeline", "show", "--issue", "22")["next_stage"], None)

        listed = {item["issue"]: item for item in self.taskctl("workspace", "list")["workspaces"]}
        self.assertEqual(listed[21]["state"]["value"], "done")
        self.assertEqual(listed[22]["state"]["reason"], "usage limit")
        self.assertEqual(listed[22]["lease"]["owner"], "claude:host:3")
        self.assertEqual(cmd("git", "status", "--porcelain", cwd=self.root).stdout, "?? .agent-workflow/\n")


if __name__ == "__main__":
    unittest.main()
