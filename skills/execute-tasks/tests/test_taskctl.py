import json
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "taskctl.py"


def cmd(*args, cwd=None, ok=True, input_text=None):
    result = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, input=input_text)
    if ok and result.returncode:
        raise AssertionError(f"command error: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


class TaskCtlTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        cmd("git", "init", "-b", "main", cwd=self.root)
        cmd("git", "config", "user.name", "Test Agent", cwd=self.root)
        cmd("git", "config", "user.email", "agent@example.invalid", cwd=self.root)
        (self.root / "README.md").write_text("initial\n", encoding="utf-8")
        cmd("git", "add", "README.md", cwd=self.root)
        cmd("git", "commit", "-m", "chore: initial", cwd=self.root)
        cmd("git", "switch", "-c", "feature/test-workflow", cwd=self.root)
        self.plan = self.root / "docs" / "TASKS.md"
        self.plan.parent.mkdir()
        self.plan.write_text("""# Tasks
Source: approved artifact
Source revision: document-v1
Source digest: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Plan approval: approved

## T001: base
- Depends on: none
- Goal: build base
- Verification: test base

## T002: feature
- Depends on: T001
- Goal: implement feature
- Verification: test feature
""", encoding="utf-8")
        cmd("git", "add", "docs/TASKS.md", cwd=self.root)
        cmd("git", "commit", "-m", "docs: add approved task plan", cwd=self.root)
        self.task("init", "--base-branch", "main")

    def task(self, command, *args, ok=True):
        result = cmd(
            "python3", str(SCRIPT), command, "--plan", str(self.plan), *args,
            cwd=self.root, ok=ok,
        )
        return json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def commit_change(self, message, content):
        (self.root / "README.md").write_text(content, encoding="utf-8")
        cmd("git", "add", "README.md", cwd=self.root)
        cmd("git", "commit", "-m", message, cwd=self.root)
        return cmd("git", "rev-parse", "HEAD", cwd=self.root).stdout.strip()

    def receipt(self, name, task_id=None):
        sha = cmd("git", "rev-parse", "HEAD", cwd=self.root).stdout.strip()
        payload = {
            "commit_sha": sha,
            "acceptance": "passed",
            "checks": [{"command": "python3 -m unittest", "status": "passed", "notes": "ok"}],
            "limitations": [],
        }
        if task_id:
            payload.update({"task_id": task_id, "diff_review": "passed"})
        path = self.root.parent / f"{self.root.name}-{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.addCleanup(path.unlink)
        return path

    def complete_task(self, task_id, content):
        self.task("start", "--task", task_id)
        self.commit_change(f"feat: complete {task_id}", content)
        receipt = self.receipt(task_id, task_id)
        return self.task("complete", "--task", task_id, "--evidence", str(receipt))

    def test_validate_init_status_and_next(self):
        result = self.task("validate")
        self.assertEqual(result["task_count"], 2)
        self.assertTrue(result["approved"])
        self.assertEqual(result["source_digest"], "sha256:" + "a" * 64)
        self.assertEqual(self.task("next")["next"]["id"], "T001")
        status = self.task("status")
        self.assertEqual(status["tasks"][0]["status"], "pending")
        self.assertEqual(status["branch"], "feature/test-workflow")
        self.assertEqual(status["base_branch"], "main")
        self.assertEqual(status["whole_plan_verification"], "missing")

    def test_sequence_success(self):
        self.task("start", "--task", "T001")
        self.assertEqual(self.task("next")["next"]["id"], "T001")
        self.commit_change("feat: base", "first\n")
        receipt = self.receipt("T001", "T001")
        result = self.task("complete", "--task", "T001", "--evidence", str(receipt))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.task("next")["next"]["id"], "T002")

    def test_cannot_skip_or_start_second(self):
        result = self.task("start", "--task", "T002", ok=False)
        self.assertFalse(result["ok"])
        self.task("start", "--task", "T001")
        result = self.task("start", "--task", "T002", ok=False)
        self.assertFalse(result["ok"])

    def test_block_and_resume(self):
        self.task("start", "--task", "T001")
        self.task("block", "--task", "T001", "--reason", "db unavailable")
        self.assertIn("Blocked", self.task("next", ok=False)["error"])
        self.assertEqual(self.task("resume", "--task", "T001")["status"], "in_progress")
        self.assertEqual(self.task("next")["next"]["id"], "T001")

    def test_dirty_tree_rejected(self):
        (self.root / "notes.txt").write_text("user owned", encoding="utf-8")
        self.assertIn("not clean", self.task("start", "--task", "T001", ok=False)["error"])

    def test_changed_plan_requires_committed_approved_sync(self):
        self.task("start", "--task", "T001")
        self.plan.write_text(self.plan.read_text().replace("test feature", "test feature changed"))
        self.assertIn("Plan changed", self.task("status", ok=False)["error"])
        self.assertIn("not clean", self.task("sync-plan", "--approved", ok=False)["error"])
        cmd("git", "add", "docs/TASKS.md", cwd=self.root)
        cmd("git", "commit", "-m", "docs: revise approved plan", cwd=self.root)
        self.assertTrue(self.task("sync-plan", "--approved")["synced"])

    def test_completed_task_definition_is_immutable(self):
        self.complete_task("T001", "completed\n")
        self.plan.write_text(self.plan.read_text().replace("test base", "changed completed task"))
        cmd("git", "add", "docs/TASKS.md", cwd=self.root)
        cmd("git", "commit", "-m", "docs: invalid completed task edit", cwd=self.root)
        self.assertIn("completed task", self.task("sync-plan", "--approved", ok=False)["error"])

    def test_unapproved_not_executable(self):
        self.plan.write_text(self.plan.read_text().replace("Plan approval: approved", "Plan approval: draft"))
        self.assertFalse(self.task("validate")["approved"])
        self.assertIn("not approved", self.task("next", ok=False)["error"])

    def test_invalid_dependency(self):
        self.plan.write_text(self.plan.read_text().replace("- Depends on: none", "- Depends on: T002", 1))
        self.assertIn("must exist earlier", self.task("validate", ok=False)["error"])

    def test_github_issue_plan_requires_valid_source_digest(self):
        content = self.plan.read_text(encoding="utf-8")
        content = content.replace("Source: approved artifact", "Source: https://github.com/acme/project/issues/7")
        content = content.replace("Source digest: sha256:" + "a" * 64, "Source digest: pending")
        self.plan.write_text(content, encoding="utf-8")
        self.assertIn("Source digest", self.task("validate", ok=False)["error"])

    def test_evidence_mismatch(self):
        self.task("start", "--task", "T001")
        self.commit_change("feat: test", "changed\n")
        receipt = self.receipt("bad", "T001")
        payload = json.loads(receipt.read_text())
        payload["checks"][0]["status"] = "failed"
        receipt.write_text(json.dumps(payload))
        self.assertIn(
            "passing check",
            self.task("complete", "--task", "T001", "--evidence", str(receipt), ok=False)["error"],
        )

    def test_branch_mismatch(self):
        self.task("start", "--task", "T001")
        cmd("git", "switch", "-c", "other", cwd=self.root)
        self.assertIn(
            "Branch mismatch",
            self.task("block", "--task", "T001", "--reason", "x", ok=False)["error"],
        )

    def test_init_rejects_base_branch_and_uncommitted_plan(self):
        plan_content = self.plan.read_text(encoding="utf-8")
        state_path = Path(cmd("git", "rev-parse", "--git-path", "agent-workflow/progress.json", cwd=self.root).stdout.strip())
        if not state_path.is_absolute():
            state_path = self.root / state_path
        state_path.unlink()
        cmd("git", "switch", "main", cwd=self.root)
        external_plan = self.root / "TASKS.md"
        external_plan.write_text(plan_content, encoding="utf-8")
        result = cmd(
            "python3", str(SCRIPT), "init", "--plan", str(external_plan), "--base-branch", "main",
            cwd=self.root, ok=False,
        )
        self.assertIn("feature branch", json.loads(result.stderr)["error"])
        cmd("git", "switch", "feature/test-workflow", cwd=self.root)
        result = cmd(
            "python3", str(SCRIPT), "init", "--plan", str(external_plan), "--base-branch", "main",
            cwd=self.root, ok=False,
        )
        self.assertIn("not clean", json.loads(result.stderr)["error"])

    def test_new_project_can_initialize_on_current_branch_without_base(self):
        plan_content = self.plan.read_text(encoding="utf-8")
        state_path = Path(cmd(
            "git", "rev-parse", "--git-path", "agent-workflow/progress.json", cwd=self.root,
        ).stdout.strip())
        if not state_path.is_absolute():
            state_path = self.root / state_path
        state_path.unlink()
        cmd("git", "switch", "main", cwd=self.root)
        self.plan.parent.mkdir(exist_ok=True)
        self.plan.write_text(plan_content, encoding="utf-8")
        cmd("git", "add", "docs/TASKS.md", cwd=self.root)
        cmd("git", "commit", "-m", "docs: add new-project plan", cwd=self.root)
        result = self.task("init")
        self.assertTrue(result["initialized"])
        self.assertEqual(result["branch"], "main")
        self.assertIsNone(result["base_branch"])

    def test_github_issue_requires_feature_branch_and_base(self):
        state_path = Path(cmd(
            "git", "rev-parse", "--git-path", "agent-workflow/progress.json", cwd=self.root,
        ).stdout.strip())
        if not state_path.is_absolute():
            state_path = self.root / state_path
        state_path.unlink()
        content = self.plan.read_text(encoding="utf-8").replace(
            "Source: approved artifact", "Source: https://github.com/acme/project/issues/7",
        )
        self.plan.write_text(content, encoding="utf-8")
        cmd("git", "add", "docs/TASKS.md", cwd=self.root)
        cmd("git", "commit", "-m", "docs: use issue source", cwd=self.root)
        self.assertIn("requires `--base-branch`", self.task("init", ok=False)["error"])

    def test_whole_plan_verification_and_pr_evidence(self):
        self.complete_task("T001", "one\n")
        self.complete_task("T002", "two\n")
        self.assertIn("current whole-plan", self.task("pr-evidence", ok=False)["error"])
        whole_receipt = self.receipt("whole-plan")
        self.assertTrue(self.task("verify-plan", "--evidence", str(whole_receipt))["verified"])
        evidence = self.task("pr-evidence")
        self.assertTrue(evidence["ready_for_pr"])
        self.assertEqual(evidence["feature_branch"], "feature/test-workflow")
        self.assertEqual(evidence["base_branch"], "main")
        self.assertEqual(len(evidence["tasks"]), 2)
        self.assertEqual(self.task("status")["whole_plan_verification"], "current")
        self.commit_change("docs: post-verification change", "stale\n")
        self.assertEqual(self.task("status")["whole_plan_verification"], "stale")
        self.assertIn("current whole-plan", self.task("pr-evidence", ok=False)["error"])

    def test_external_plan_under_git_metadata_is_preserved(self):
        state_path = Path(cmd(
            "git", "rev-parse", "--git-path", "agent-workflow/progress.json", cwd=self.root,
        ).stdout.strip())
        if not state_path.is_absolute():
            state_path = self.root / state_path
        state_path.unlink()
        external_plan = state_path.parent / "TASKS.md"
        external_plan.parent.mkdir(parents=True, exist_ok=True)
        external_plan.write_text(self.plan.read_text(encoding="utf-8"), encoding="utf-8")
        result = cmd(
            "python3", str(SCRIPT), "init", "--plan", str(external_plan),
            "--base-branch", "main", cwd=self.root,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["plan_storage"], "git-metadata")
        self.assertTrue(external_plan.exists())

    def test_issue_digest_ignores_updated_at_but_detects_content(self):
        issue = {
            "title": "Fix behavior",
            "body": "Expected result",
            "state": "OPEN",
            "labels": [{"name": "bug"}],
            "comments": [{"id": "C1", "body": "Reproduction"}],
            "updatedAt": "2026-01-01T00:00:00Z",
        }
        first = cmd(
            "python3", str(SCRIPT), "source-digest", "--input", "-", cwd=self.root,
            input_text=json.dumps(issue),
        )
        issue["updatedAt"] = "2026-02-01T00:00:00Z"
        second = cmd(
            "python3", str(SCRIPT), "source-digest", "--input", "-", cwd=self.root,
            input_text=json.dumps(issue),
        )
        self.assertEqual(json.loads(first.stdout)["source_digest"], json.loads(second.stdout)["source_digest"])
        issue["body"] = "Different result"
        third = cmd(
            "python3", str(SCRIPT), "source-digest", "--input", "-", cwd=self.root,
            input_text=json.dumps(issue),
        )
        self.assertNotEqual(json.loads(first.stdout)["source_digest"], json.loads(third.stdout)["source_digest"])


class OverlapTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def plan(self, name, *touches):
        lines = ["# Tasks", "Plan approval: draft", ""]
        for index, touch in enumerate(touches, start=1):
            lines += [f"## T{index:03d}: task {index}", "- Depends on: none"]
            if touch is not None:
                lines.append(f"- Touches: {touch}")
            lines.append("")
        path = self.root / f"{name}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)

    def overlap(self, *plans, ok=True):
        result = cmd("python3", str(SCRIPT), "overlap", "--plans", *plans, cwd=self.root, ok=ok)
        return json.loads(result.stdout if result.returncode == 0 else result.stderr)

    def test_disjoint_plans_are_parallel(self):
        result = self.overlap(self.plan("a", "src/auth/*.py, docs/auth.md"), self.plan("b", "src/api/, README.md"))
        self.assertEqual(result["verdict"], "parallel")
        self.assertEqual(result["conflicts"], [])

    def test_shared_file_or_glob_intersection_is_sequential(self):
        result = self.overlap(self.plan("a", "src/api/routes.py"), self.plan("b", "src/api/*.py"))
        self.assertEqual(result["verdict"], "sequential")
        self.assertEqual(result["conflicts"][0]["paths"], [["src/api/routes.py", "src/api/*.py"]])
        result = self.overlap(self.plan("c", "src/"), self.plan("d", "src/api/**"))
        self.assertEqual(result["verdict"], "sequential")
        result = self.overlap(self.plan("e", "README.md"), self.plan("f", "README.md"))
        self.assertEqual(result["verdict"], "sequential")

    def test_shared_marker_conflicts_with_every_other_plan(self):
        result = self.overlap(self.plan("a", "shared:package-lock.json"), self.plan("b", "src/x.py"))
        self.assertEqual(result["verdict"], "sequential")

    def test_missing_touches_is_unknown_but_valid(self):
        missing = self.plan("a", "src/x.py", None)
        result = self.overlap(missing, self.plan("b", "docs/y.md"))
        self.assertEqual(result["verdict"], "sequential")
        self.assertEqual(result["unknown"], [{"plan": str(Path(missing).resolve()), "tasks": ["T002"]}])
        validated = cmd("python3", str(SCRIPT), "validate", "--plan", missing, cwd=self.root)
        self.assertTrue(json.loads(validated.stdout)["valid"])

    def test_more_than_one_touches_line_is_invalid(self):
        path = self.root / "bad.md"
        path.write_text("# Tasks\n\n## T001: x\n- Depends on: none\n- Touches: a\n- Touches: b\n", encoding="utf-8")
        error = cmd("python3", str(SCRIPT), "validate", "--plan", str(path), cwd=self.root, ok=False)
        self.assertIn("at most one `- Touches:`", json.loads(error.stderr)["error"])


if __name__ == "__main__":
    unittest.main()
