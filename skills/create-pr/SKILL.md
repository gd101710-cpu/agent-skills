---
name: create-pr
description: On explicit user authorization, publish an existing verified change set as a GitHub PR using a local agent CLI (Codex CLI or Claude Code) and gh; verify fork/upstream base, issue references, PR template, and result without implementing or merging.
---

# Create PR — publication only

Read [references/pr-publishing.md](references/pr-publishing.md) for exact checklist and CLI examples. Invoke sibling `$write-ste` when installed for clear PR wording; if not present, follow the same clarity rules locally without claiming the skill ran.

## Language
Explain the proposed PR, scope, validation, and any required approval request to the user in Korean. Draft and publish GitHub PR titles and bodies in English. When requesting approval, pair a Korean explanation with the exact English title and body to be published; keep the Korean explanation outside the published text. Preserve required template headings, code, logs, identifiers, and quotations as written. Follow a different language only when the user explicitly requests it. This language rule does not add another approval step when publication is already authorized.

## Scope and preflight
1. Publication requires the user's explicit request (`$create-pr`, or an equivalent clearly authorized PR-publish instruction). `$execute-tasks` does not itself authorize a PR. Do not merge, enable auto-merge, reimplement code, or fix unrelated CI. No worker agents.
   The user may optionally run `$explain-diff` before this skill; its Notion page is learning context, not verification evidence or publication authorization.
2. For an issue-backed change, resolve the issue worktree with sibling `execute-tasks/scripts/taskctl.py workspace get --issue <N>` (by its resolved real path) and run every Git and evidence command there, with no options before the subcommand (no `git -C`). Read `AGENTS.md`, `CONTRIBUTING.md`, PR template, current branch/remote, intended base repo and branch, change diff, related issue. Locate the execute ledger via `git rev-parse --git-path agent-workflow/progress.json`, read its exact `plan_path`, and run sibling `execute-tasks/scripts/taskctl.py pr-evidence --plan <plan>`. Publish only the recorded feature branch to the recorded base branch; reject a branch/HEAD mismatch or stale/missing whole-plan evidence. For OSS, also confirm the head is the **user's fork branch** and the base is the **actual upstream repository**. Do not guess owner from `origin` alone.
3. Verify exact issue completion: **fully resolved** → standalone `Closes owner/repo#123` (or `Closes #123` for same repo), **partially related** → `Refs ...`. A closing keyword in a stacked or non-default base may not close the issue automatically. Do not falsely promise closure.
4. Use the task and whole-plan receipts returned by `pr-evidence` as the validation source. Do not run new validation merely for PR writing or publish when that evidence is unavailable/stale; hand back to `$execute-tasks` for verification. Check the recorded head commit SHA and intended diff; if local source is dirty, report and resolve scope before pushing.
5. Ask only for ambiguous branch/base, target, issue identity, or user authorization. No speculative fork creation or force push.

## Publish exactly once
1. Write an English Conventional Commit-like title and GitHub PR body following the Language section, existing template, code changes, risks and actual test results. Include AI-use disclosure when required by repo or user, not invented 'human reviewed' claims.
2. `gh auth status`, then `gh pr list --head <branch>` / `gh pr view` to find existing matching PR. **Reuse**, don't duplicate. Push local branch only when authorized and correct remote is established: `git push -u <head-remote> <head-branch>` (no force).
3. Use safe `--body-file` and explicit `--repo <upstream>`/`--base`/`--head owner:branch` when needed. Create draft if review-readiness or contribution guidelines require it; otherwise non-draft, respecting user's explicit choice.
4. Re-fetch the resulting PR. Verify URL, head/base repos, branch, state, issue references, validation text and no lost template sections. If a command has uncertain outcome, inspect GitHub state before any retry.
5. Report PR URL, head SHA, checked/tested coverage and pending CI/review. Stop. `$repair-pr` is a separate explicit action.
