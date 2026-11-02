# PR publishing checklist (Codex CLI or Claude Code + gh)

Run commands from target git checkout and inspect actual output; substitute exact host, repository, branch and path values. Requires Git, GitHub CLI, authentication and permissions.

```bash
git status --short
git branch --show-current
git remote -v
git log -1 --format='%H %s'
git rev-parse --git-path agent-workflow/progress.json
# Read plan_path from that ledger, then:
# <execute-tasks> is the sibling execute-tasks directory next to the loaded create-pr skill.
python3 <execute-tasks>/scripts/taskctl.py pr-evidence --plan <plan-path>
gh auth status
gh repo view --json nameWithOwner,defaultBranchRef
# Also inspect CONTRIBUTING.md, AGENTS.md, .github/PULL_REQUEST_TEMPLATE*.
```

Treat the returned `feature_branch`, `base_branch`, `head_sha`, task receipts and whole-plan receipt as the local handoff contract. Read the issue URL and any previous PR, then compare repositories/remotes to that intended base. For forks, ensure correct head fork owner and the base upstream. The bare `gh pr create` defaults can be wrong on fork checkouts. Examples to adapt **only after verification**:

```bash
# Given: upstream owner/project, fork username, branch fix-issue-123
# Push to confirmed fork remote only if user authorized.
git push -u fork fix-issue-123
# This assumes the upstream accepts fork PRs and branch exists in that fork.
gh pr create --repo upstream/project --base main --head username:fix-issue-123 \
  --title 'fix(component): correct documented behavior' --body-file /tmp/pr-body.md
# For an existing PR, prefer gh pr view/edit after confirming identity.
gh pr view --repo upstream/project <PR_NUMBER> --json url,isDraft,state,baseRefName,headRefName,headRefOid,body,title
```

PR body: `Summary`, `Behavior`, `Validation`, `Risks/Compatibility`, exact template headings, and `Closes #...` or `Refs #...`. Put each issue reference on its own line outside code blocks; for cross-repo use `owner/repo#123`. Never claim validation for a changed SHA if it ran against an earlier revision; disclose unknown/not run. Never treat user instruction to create PR as permission to merge. Repository-specific contribution policies override default formatting.
