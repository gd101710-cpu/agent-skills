import json
from pathlib import Path
import tempfile
import unittest

from test_taskctl import SCRIPT, cmd


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name) / "repo"
        cmd("git", "init", "-b", "main", str(self.root))
        cmd("git", "config", "user.name", "Test Agent", cwd=self.root)
        cmd("git", "config", "user.email", "agent@example.invalid", cwd=self.root)
        (self.root / "README.md").write_text("initial\n", encoding="utf-8")
        cmd("git", "add", "README.md", cwd=self.root)
        cmd("git", "commit", "-m", "chore: initial", cwd=self.root)

    def taskctl(self, *args, ok=True):
        result = cmd("python3", str(SCRIPT), *args, cwd=self.root, ok=ok)
        return json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def write_pipeline(self, pipeline):
        path = self.root / ".agent-workflow" / "pipeline.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(pipeline) if not isinstance(pipeline, str) else pipeline, encoding="utf-8")
        return path

    def stages(self, *extra, base=True):
        stages = [{"id": "execute", "skill": "execute-tasks", "access": "local-write",
                   "modifies-code": True, "verifies": True}] if base else []
        return stages + list(extra)

    def test_default_pipeline(self):
        shown = self.taskctl("pipeline", "show")
        self.assertEqual(shown["source"], "default")
        self.assertEqual([stage["id"] for stage in shown["stages"]], ["precheck", "plan", "execute", "explain", "pr"])
        self.assertTrue(self.taskctl("pipeline", "validate")["valid"])

    def test_file_overrides_default(self):
        path = self.write_pipeline({"stages": self.stages()})
        shown = self.taskctl("pipeline", "show")
        self.assertEqual((shown["source"], [stage["id"] for stage in shown["stages"]]),
                         (str(path.resolve()), ["execute"]))

    def assert_invalid(self, pipeline, message):
        self.write_pipeline(pipeline)
        error = self.taskctl("pipeline", "validate", ok=False)
        self.assertFalse(error["ok"])
        self.assertIn(message, error["error"])

    def test_validate_rejects_unsafe_pipelines(self):
        self.assert_invalid({"stages": self.stages({"id": "x", "skill": "no-such-skill", "access": "read"})},
                            "skill not found")
        self.assert_invalid({"stages": self.stages({"id": "x", "skill": "write-ste", "access": "admin"})},
                            "access must be one of")
        self.assert_invalid({"stages": self.stages({"id": "pr", "skill": "create-pr", "access": "remote"})},
                            "remote stages require gate `approval`")
        self.assert_invalid({"stages": self.stages(
            {"id": "fix", "skill": "write-ste", "access": "local-write", "modifies-code": True},
            {"id": "pr", "skill": "create-pr", "access": "remote", "gate": "approval"})},
            "fix modifies code but is not verified before remote stage pr")
        self.assert_invalid({"stages": self.stages({"id": "execute", "skill": "write-ste", "access": "read"})},
                            "Duplicate stage id")

    def test_verifying_stage_clears_unverified_change(self):
        self.write_pipeline({"stages": self.stages(
            {"id": "fix", "skill": "write-ste", "access": "local-write", "modifies-code": True},
            {"id": "verify", "skill": "execute-tasks", "access": "local-write", "verifies": True},
            {"id": "pr", "skill": "create-pr", "access": "remote", "gate": "approval"})})
        self.assertTrue(self.taskctl("pipeline", "validate")["valid"])

    def test_invalid_json_names_file(self):
        path = self.write_pipeline("{not json")
        error = self.taskctl("pipeline", "show", ok=False)
        self.assertIn(str(path.resolve()), error["error"])

    def test_stage_progress_in_order(self):
        self.taskctl("workspace", "get", "--issue", "4")
        shown = self.taskctl("pipeline", "show", "--issue", "4")
        self.assertEqual((shown["next_stage"], shown["state"]["value"]), ("precheck", "pending"))
        error = self.taskctl("workspace", "stage", "--issue", "4", "--complete", "execute", ok=False)
        self.assertIn("cannot complete before precheck", error["error"])
        error = self.taskctl("workspace", "stage", "--issue", "4", "--complete", "deploy", ok=False)
        self.assertIn("Unknown stage", error["error"])
        self.assertEqual(self.taskctl("pipeline", "show", "--issue", "4")["completed"], [])
        for stage in ("precheck", "plan", "execute"):
            self.taskctl("workspace", "stage", "--issue", "4", "--complete", stage)
        self.assertEqual(self.taskctl("pipeline", "show", "--issue", "4")["next_stage"], "explain")
        self.taskctl("workspace", "stage", "--issue", "4", "--complete", "pr")
        shown = self.taskctl("pipeline", "show", "--issue", "4")
        self.assertEqual((shown["completed"], shown["next_stage"]), (["precheck", "plan", "execute", "pr"], None))
        self.assertEqual((shown["skipped_optional"], shown["skipped_new"]), (["explain"], []))

    def test_one_off_stage_applies_to_one_issue(self):
        for issue in ("4", "5"):
            self.taskctl("workspace", "get", "--issue", issue)
        error = self.taskctl("workspace", "stage", "--issue", "4", "--insert", "write-ste", "--after", "execute",
                             "--id", "polish", "--modifies-code", ok=False)
        self.assertIn("polish modifies code but is not verified", error["error"])
        self.taskctl("workspace", "stage", "--issue", "4", "--insert", "write-ste", "--after", "execute",
                     "--id", "polish")
        four = [stage["id"] for stage in self.taskctl("pipeline", "show", "--issue", "4")["stages"]]
        five = [stage["id"] for stage in self.taskctl("pipeline", "show", "--issue", "5")["stages"]]
        self.assertEqual(four, ["precheck", "plan", "execute", "polish", "explain", "pr"])
        self.assertNotIn("polish", five)
        error = self.taskctl("workspace", "stage", "--issue", "5", "--insert", "write-ste", "--after", "plan",
                             "--access", "remote", ok=False)
        self.assertIn("remote stages require gate", error["error"])

    def test_pipeline_edit_applies_to_remaining_stages_only(self):
        self.taskctl("workspace", "get", "--issue", "4")
        for stage in ("precheck", "plan"):
            self.taskctl("workspace", "stage", "--issue", "4", "--complete", stage)
        stages = self.taskctl("pipeline", "show")["stages"]
        early = {"id": "lint", "skill": "write-ste", "access": "read"}
        late = {"id": "review", "skill": "write-ste", "access": "read"}
        self.write_pipeline({"stages": [stages[0], early, stages[1], stages[2], late, stages[4]]})
        shown = self.taskctl("pipeline", "show", "--issue", "4")
        self.assertEqual(shown["skipped_new"], ["lint"])
        self.assertEqual(shown["next_stage"], "execute")
        self.taskctl("workspace", "stage", "--issue", "4", "--complete", "execute")
        self.assertEqual(self.taskctl("pipeline", "show", "--issue", "4")["next_stage"], "review")

    def test_run_state_is_recorded_and_listed(self):
        self.taskctl("workspace", "get", "--issue", "4")
        self.assertEqual(self.taskctl("workspace", "list")["workspaces"][0]["state"], {"value": "pending"})
        self.taskctl("workspace", "state", "--issue", "4", "--set", "interrupted", "--reason", "usage limit")
        listed = self.taskctl("workspace", "list")["workspaces"][0]["state"]
        self.assertEqual((listed["value"], listed["reason"]), ("interrupted", "usage limit"))
        error = cmd("python3", str(SCRIPT), "workspace", "state", "--issue", "4", "--set", "lost",
                    cwd=self.root, ok=False)
        self.assertIn("invalid choice", error.stderr)

    def test_validate_explicit_file(self):
        path = Path(self.temporary_directory.name) / "candidate.json"
        path.write_text(json.dumps({"stages": self.stages()}), encoding="utf-8")
        self.assertEqual(self.taskctl("pipeline", "validate", "--file", str(path))["source"], str(path.resolve()))


if __name__ == "__main__":
    unittest.main()
