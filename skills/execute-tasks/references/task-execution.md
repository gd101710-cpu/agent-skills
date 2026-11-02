# Task execution: progress and verification contract

## State
`taskctl.py` stores execution state under the current worktree's git metadata via `git rev-parse --git-path agent-workflow/progress.json` (not under the committed source tree). `init` binds it to one approved plan, execution branch, baseline SHA and, for issue work, a base branch/SHA. `status` and `next` may be run in any new Codex CLI or Claude Code conversation within the **same worktree/branch**. Each issue worktree has its own ledger, so issues in different worktrees never share state. For a new clone, bring the approved task plan and Git history, then build a fresh state file with the user's acknowledgment; unrecorded completed work should be reconciled manually and not claimed complete.

- Pending → `start` → in_progress → `complete` → completed
- in_progress → `block` → blocked → `resume` → in_progress
- A blocked task stops processing. No automatic skip.
- The helper stores plan SHA-256 and per-task fingerprints and detects plan edits and branch changes.
- Repository-local plans must be tracked and committed before `init`; external OSS plans are accepted only inside the resolved git `agent-workflow` directory. Both remain available through PR handoff.

## Required acceptance evidence (example)
Write to `/tmp/T001-verification.json` or another safe temporary path. Real data only; **do not fabricate**.

```json
{
  "task_id": "T001",
  "commit_sha": "<full git rev-parse HEAD sha>",
  "acceptance": "passed",
  "diff_review": "passed",
  "checks": [
    {"command": "python -m pytest tests/test_auth.py -q", "status": "passed", "notes": "15 passed"},
    {"command": "ruff check .", "status": "passed", "notes": "clean"}
  ],
  "limitations": []
}
```

For changes where no runtime test applies, the verification still needs a *performed*, concrete check; do not call an unperformed build "passed". Use an appropriate static diff/docs/check and state uncovered risks.

## Commands
```bash
python3 <this-skill>/scripts/taskctl.py validate --plan docs/TASKS.md
# Issue-backed maintenance or OSS:
python3 <this-skill>/scripts/taskctl.py init --plan docs/TASKS.md --base-branch main
# New project (stay on the current branch):
python3 <this-skill>/scripts/taskctl.py init --plan docs/TASKS.md
python3 <this-skill>/scripts/taskctl.py status --plan docs/TASKS.md
python3 <this-skill>/scripts/taskctl.py next --plan docs/TASKS.md
python3 <this-skill>/scripts/taskctl.py start --plan docs/TASKS.md --task T001
python3 <this-skill>/scripts/taskctl.py complete --plan docs/TASKS.md --task T001 --evidence /tmp/T001-verification.json
python3 <this-skill>/scripts/taskctl.py block --plan docs/TASKS.md --task T002 --reason "integration database unavailable"
python3 <this-skill>/scripts/taskctl.py resume --plan docs/TASKS.md --task T002
python3 <this-skill>/scripts/taskctl.py verify-plan --plan docs/TASKS.md --evidence /tmp/whole-plan-verification.json
python3 <this-skill>/scripts/taskctl.py pr-evidence --plan docs/TASKS.md
# Issue workspaces (shared registry under the Git common directory):
python3 <this-skill>/scripts/taskctl.py workspace get --issue 123 --base main
python3 <this-skill>/scripts/taskctl.py workspace claim --issue 123 --owner <session-id>
python3 <this-skill>/scripts/taskctl.py workspace release --issue 123 --owner <session-id>
python3 <this-skill>/scripts/taskctl.py workspace list
python3 <this-skill>/scripts/taskctl.py workspace remove --issue 123
python3 <this-skill>/scripts/taskctl.py overlap --plans <plan-a> <plan-b>
```

`<this-skill>` is the real path of the directory of the loaded `execute-tasks/SKILL.md`; resolve it, including symlinks, in the current session instead of assuming an install path. The script resolves state from the current Git checkout, not from its own location. Substitute the absolute path in each command; agent shells may not keep variables between commands. After a task plan revision approved by the user, call `sync-plan --approved` only after reviewing the diff. Sync refuses changes to completed task definitions; active/blocked tasks may be revised only after user approval and when all new dependencies are already completed.

For maintenance issues, save `gh issue view --json title,body,state,labels,comments` output temporarily and run `taskctl.py source-digest --input <json-path>`. The canonical digest covers title, body, state, sorted label names, and comment IDs/bodies; it ignores `updatedAt` and other timestamps. Compare this value with the plan's `Source digest`.

## Whole-plan evidence
After every task is completed, use the same receipt shape without `task_id` or `diff_review`:

```json
{
  "commit_sha": "<full git rev-parse HEAD sha>",
  "acceptance": "passed",
  "checks": [
    {"command": "python -m pytest", "status": "passed", "notes": "124 passed"}
  ],
  "limitations": []
}
```

`verify-plan` stores this receipt. Any later commit makes it stale. `pr-evidence` succeeds only when all tasks are complete, the checkout is clean and on the recorded feature branch, and whole-plan evidence matches HEAD; it returns the exact branch/base/SHAs and task plus whole-plan receipts for `$create-pr`.

## Important limitations
- Test receipts are agent-provided evidence, **not cryptographic proof of a test run**. A separate CI is necessary for higher assurance.
- Committing a correct task does not mean the entire project is done; whole-plan verification is separate.
- The helper cannot distinguish all accidental source edits; compare diffs before staging and committing.
- No background monitoring, scheduling, PR creation or remote write.
