import json
from pathlib import Path
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "issue_order.py"


def issue(number, *deps, body=None):
    if body is None:
        body = "## Dependencies\n- Depends on: " + (", ".join(f"#{dep}" for dep in deps) or "none") + "\n"
    return {"number": number, "title": f"Issue {number}", "body": body}


class IssueOrderTests(unittest.TestCase):
    def order(self, issues, *args, ok=True):
        payload = issues if isinstance(issues, str) else json.dumps(issues)
        result = subprocess.run(["python3", str(SCRIPT), "--issues", "-", *args], input=payload,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        return json.loads(result.stdout) if ok else json.loads(result.stderr)

    def test_one_chain_when_every_issue_depends_on_the_previous(self):
        result = self.order([issue(1, 4), issue(2, 3), issue(3), issue(4, 2)])
        self.assertEqual(result["tracks"], [[3, 2, 4, 1]])
        self.assertEqual((result["start_now"], result["order"]), ([3], [3, 2, 4, 1]))
        self.assertEqual(result["issues"]["1"]["status"], "waiting")

    def test_independent_chains_start_in_parallel(self):
        result = self.order([issue(1, 4), issue(2, 3), issue(3), issue(4)])
        self.assertEqual(result["tracks"], [[3, 2], [4, 1]])
        self.assertEqual(result["start_now"], [3, 4])
        self.assertEqual(result["order"], [3, 2, 4, 1])

    def test_declaration_forms_and_external_references(self):
        bodies = [
            issue(5, body="Blocked by #6 and #99\n"),
            issue(6, body="* depends on #7\nMentions #5 in prose only.\n"),
            issue(7, body="No dependencies. Relates to #6.\n"),
        ]
        result = self.order(bodies)
        self.assertEqual(result["tracks"], [[7, 6, 5]])
        self.assertEqual(result["external"], {"5": [99]})
        self.assertEqual(result["issues"]["5"]["depends_on"], [6])

    def test_inferred_edges_conflicts_and_active_issues(self):
        issues = [issue(1), issue(2), issue(3), issue(4)]
        result = self.order(issues, "--depends", "4:1", "--conflict", "2:3", "--active", "1")
        self.assertEqual(result["tracks"], [[1, 4], [2, 3]])
        self.assertEqual((result["ready"], result["start_now"]), ([2, 3], [2]))
        self.assertEqual(result["issues"]["1"]["status"], "active")
        self.assertEqual(result["issues"]["4"]["status"], "waiting")
        blocked = self.order(issues, "--conflict", "2:3", "--active", "3")
        self.assertEqual(blocked["start_now"], [1, 4])
        self.assertEqual(blocked["issues"]["2"]["status"], "waiting")

    def test_cycles_are_reported_and_block_dependents(self):
        result = self.order([issue(1, 2), issue(2, 1), issue(3, 1), issue(4)])
        self.assertEqual(result["cycles"], [1, 2])
        self.assertEqual(result["issues"]["3"]["status"], "blocked-by-cycle")
        self.assertEqual((result["tracks"], result["start_now"]), ([[4]], [4]))

    def test_text_format_and_invalid_input(self):
        text = subprocess.run(["python3", str(SCRIPT), "--issues", "-", "--format", "text"],
                              input=json.dumps([issue(1, 2), issue(2)]), capture_output=True, text=True).stdout
        self.assertIn("Track 1: #2 -> #1", text)
        self.assertIn("Start now (one terminal each): #2", text)
        self.assertIn("Invalid issue list", self.order("{", ok=False)["error"])
        result = subprocess.run(["python3", str(SCRIPT), "--issues", "-", "--depends", "3:3"],
                                input="[]", capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
