---
name: cleanup-branch
description: Finish work after PR merge by inspecting the current repository's remaining local and remote work branches, deleting those verified against merged PRs, and returning to an updated base branch. An explicit PR narrows cleanup to that PR.
---

# Cleanup Branch — after confirmed PR merge

## Scope
- Use this as the final step after completing work and merging its PR. A bare invocation authorizes inspection of all remaining local and remote work branches in the current repository and cleanup of those that satisfy the checks below. Discover candidates even when the checkout is already on the default/base branch; do not require the user to name a PR first.
- A supplied PR URL/number or branch explicitly narrows the scope. Otherwise inspect all candidates, including branches from earlier completed work. Ask only when repository identity or the destination base cannot be resolved; preserve ambiguous candidates and continue with independently verified ones.
- Remote cleanup covers the current repository and its user-owned or authorized head forks, not unrelated repositories or other contributors' branches. Do not merge, publish a PR, edit code, or monitor in the background. An open or merely closed, unmerged PR does not qualify.
- Preserve uncommitted work, post-PR commits, protected/default/base branches, other worktrees, approved plans and execution ledgers. Never reset, clean, stash, or bypass remote protections to finish cleanup.

## Discover and verify candidates
1. Read `AGENTS.md` and relevant repository contribution rules. Inspect `git status --short`, pending Git operations, `git branch --show-current`, `git remote -v`, and `git worktree list --porcelain`. A dirty checkout or an in-progress merge/rebase → report the blocker and stop before mutations.
2. Resolve the current repository, its default branch, configured remotes, authenticated user, and repository permissions. Enumerate local heads with their upstreams and actual remote heads in the authorized repositories, including remote-only work branches. Use `git ls-remote --heads` rather than stale remote-tracking refs as proof of current remote state. Resolve head forks to their actual URLs; do not infer repository identity from `origin` or branch names alone.
3. Find associated PRs in the current base repository, matching both head repository identity and branch name. Paginate discovery results. For each candidate, query the exact PR against its base repository:
   ```bash
   gh pr view --repo <base-owner/repo> <number> --json url,state,mergedAt,headRefName,headRefOid,headRepository,headRepositoryOwner,baseRefName
   ```
   Require `state: MERGED` and a non-null `mergedAt`. Confirm the head belongs to the user or a repository they are authorized to maintain. Preserve candidates with no PR, missing/ambiguous identity or head SHA, or any open PR using the same head repository and branch. A historical merged PR alone does not qualify a reused branch for deletion.
4. Inspect default branches and applicable branch protections in the base and head repositories. Exclude those branches and the base branches of the matched PRs from deletion. Read local head refs and the actual remote head with `git ls-remote --heads <head-remote> refs/heads/<head-branch>`; a failed remote query is not proof of absence. Each existing ref is eligible only when its tip exactly equals a confirmed merged PR's `headRefOid`. Preserve newer or divergent tips and report them independently; an already absent ref requires no deletion. If the local branch's upstream points elsewhere, resolve that mismatch before treating it as this PR's branch. Do not use age, branch names, or ancestry alone to infer eligibility.

## Return to base and delete eligible refs
1. Choose the destination before deleting anything: use the explicit PR's base, otherwise the common base of eligible PRs, or the current repository's default branch when eligible PRs have different bases. If no refs qualify, report the findings without mutations. Fetch the confirmed base remote. Switch to the existing local destination branch, or create it tracking the confirmed remote base if absent. Verify an existing base branch's tracking target before updating it. Update with `git merge --ff-only <base-remote>/<base-branch>`. If switching or updating fails, stop and report; do not rewrite a diverged base or disturb another worktree.
2. For each verified candidate, recheck the local head tip and worktree usage. If a registered issue workspace holds the branch (sibling `execute-tasks/scripts/taskctl.py workspace list`, called by its resolved real path), run `workspace remove --issue <N>` first; it archives the worktree's execution ledger under the Git common directory and removes the worktree and registry entry. If it refuses because the worktree is dirty or claimed, preserve the worktree and branch and report why. Skip local deletion if any other worktree has that branch checked out; never remove unregistered worktrees. Delete an eligible local head with `git branch -d <head-branch>`, run from the destination checkout with no options before the subcommand (no `git -C`).
   Squash/rebase merges can fail this ancestry check. Only for that case, reconfirm the PR is merged and the local tip exactly equals its PR head SHA, then use `git branch -D <head-branch>`. Other deletion failures are blockers, not reasons to force deletion.
3. Recheck the remote head. If still present at the PR head SHA, delete only that exact revision using an explicit lease to protect commits pushed since the check:
   ```bash
   git push --force-with-lease=refs/heads/<head-branch>:<PR-head-SHA> <head-remote> --delete <head-branch>
   ```
   The lease is restricted to deletion of the verified PR head; it does not authorize rewriting a published branch. If it fails, inspect the remote again and preserve changed tips. Treat an already deleted remote branch as complete; respect protection/permission failures without bypasses.
4. Process candidates independently: a blocked or preserved ref does not prevent cleanup of other verified refs. Stop on repository-wide failures such as authentication loss or a failed base update. Verify the remaining checkout branch and each candidate's local and remote state. Report matched PR URLs and merge confirmation, base update result, and separate local/remote cleanup results, including preserved refs and reasons. Do not claim full cleanup if any requested deletion remains blocked. Retain workflow history for later reference.
