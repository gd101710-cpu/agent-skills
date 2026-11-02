import json
from pathlib import Path
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TASKCTL = REPOSITORY_ROOT / "skills" / "execute-tasks" / "scripts" / "taskctl.py"
PLAN_TEMPLATE = REPOSITORY_ROOT / "skills" / "plan-tasks" / "assets" / "TASKS.template.md"


def run(*args, cwd, ok=True):
    result = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True)
    if ok and result.returncode:
        raise AssertionError(f"command error: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result


class WorkflowIntegrationTests(unittest.TestCase):
    def test_plan_template_executes_and_exports_pr_handoff(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            run("git", "init", "-b", "main", cwd=root)
            run("git", "config", "user.name", "Integration Agent", cwd=root)
            run("git", "config", "user.email", "agent@example.invalid", cwd=root)
            (root / "README.md").write_text("base\n", encoding="utf-8")
            run("git", "add", "README.md", cwd=root)
            run("git", "commit", "-m", "chore: initial", cwd=root)
            run("git", "switch", "-c", "feature/template-contract", cwd=root)

            plan = root / "docs" / "TASKS.md"
            plan.parent.mkdir()
            content = PLAN_TEMPLATE.read_text(encoding="utf-8")
            content = content.replace("Plan approval: draft", "Plan approval: approved")
            content = content.replace(
                "Source digest: <sha256:... for GitHub issue content; omit for immutable local documents>",
                "Source digest: sha256:" + "b" * 64,
            )
            plan.write_text(content, encoding="utf-8")
            run("git", "add", "docs/TASKS.md", cwd=root)
            run("git", "commit", "-m", "docs: approved planning baseline", cwd=root)

            def taskctl(command, *args):
                result = run(
                    "python3", str(TASKCTL), command, "--plan", str(plan), *args, cwd=root,
                )
                return json.loads(result.stdout)

            validation = taskctl("validate")
            self.assertEqual(validation["task_count"], 2)
            taskctl("init", "--base-branch", "main")

            for task_id in ("T001", "T002"):
                taskctl("start", "--task", task_id)
                (root / "README.md").write_text(f"completed {task_id}\n", encoding="utf-8")
                run("git", "add", "README.md", cwd=root)
                run("git", "commit", "-m", f"feat: complete {task_id}", cwd=root)
                head = run("git", "rev-parse", "HEAD", cwd=root).stdout.strip()
                receipt = root.parent / f"{root.name}-{task_id}.json"
                receipt.write_text(json.dumps({
                    "task_id": task_id,
                    "commit_sha": head,
                    "acceptance": "passed",
                    "diff_review": "passed",
                    "checks": [{"command": "git diff --check", "status": "passed"}],
                    "limitations": [],
                }), encoding="utf-8")
                self.addCleanup(receipt.unlink)
                taskctl("complete", "--task", task_id, "--evidence", str(receipt))

            head = run("git", "rev-parse", "HEAD", cwd=root).stdout.strip()
            whole_receipt = root.parent / f"{root.name}-whole-plan.json"
            whole_receipt.write_text(json.dumps({
                "commit_sha": head,
                "acceptance": "passed",
                "checks": [{"command": "python3 -m unittest", "status": "passed"}],
                "limitations": [],
            }), encoding="utf-8")
            self.addCleanup(whole_receipt.unlink)
            taskctl("verify-plan", "--evidence", str(whole_receipt))
            handoff = taskctl("pr-evidence")

            self.assertTrue(handoff["ready_for_pr"])
            self.assertEqual(handoff["feature_branch"], "feature/template-contract")
            self.assertEqual(handoff["base_branch"], "main")
            self.assertEqual(handoff["head_sha"], head)
            self.assertEqual(len(handoff["tasks"]), 2)


if __name__ == "__main__":
    unittest.main()
