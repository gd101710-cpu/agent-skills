---
name: repair-pr
description: On explicit user request, repair actionable maintainer feedback, merge conflicts, or failing CI in an existing ordinary PR; test and push scoped fixes without merging or auto-resolving reviewer conversations.
---

# Repair PR — one PR, one pass

## Preconditions
- User explicitly identifies PR URL/number or unambiguous current PR and authorizes repair. If the PR's head branch belongs to a registered issue workspace (sibling `execute-tasks/scripts/taskctl.py workspace list`, called by its resolved real path), work in that worktree; otherwise use the existing branch in the current checkout as before. Run Git with the working checkout as the working directory and no options before the subcommand (no `git -C`). Use existing branch; for OSS confirm fork head and upstream base. Read `AGENTS.md`, `CONTRIBUTING.md`, repository PR/review policies.
- Inspect `git status`, pending operations, head SHA, current GitHub PR state and expected branch. Dirty workspace or ambiguity → pause rather than discard changes. Do not use stack-maintenance tools or subagents.
- Gather relevant CI check conclusions and failed logs via `gh pr checks` / `gh run view --log-failed` where allowed; read unresolved maintainer and other reviewer feedback. Distinguish stale findings, suggestions and actionable defects.

## Fix loop
1. Reproduce or trace each finding against the correct current head. Group duplicate findings by underlying cause; do **not** fix unrelated pre-existing failures or broaden the user-approved issue scope.
2. First determine whether a merge conflict needs resolution. Prefer repository's documented method (merge or rebase), never rewrite published history/force-push without explicit user authorization and review of consequences. If change touches upstream behavior/data contract, ask before implementing controversial changes.
3. Fix actionable problems in bounded units; run focused and affected regression tests, lint/build as required. Review diff. Record actual executed checks and uncovered risks.
4. Commit each coherent repair cause locally; push only to the **confirmed existing PR head** via non-force push after authorization. Before push, verify no remote branch divergence and no third-party commits would be lost.
5. Re-fetch PR status, new SHA and relevant checks. CI may still be pending; do not assert it is green. Report fixed issues, evidence, unresolved/invalid/out-of-scope findings and exact PR URL. Stop after this pass; no periodic polling or background processing.

## Public conversation policy
- Do not post comments, submit reviews, resolve reviewer threads or merge without **separate explicit authorization**. Prepare suggested replies in chat. Maintainer feedback has priority over generic style advice, but never silently violate source or user constraints.
- No edit of another contributor's unowned branch, secret handling shortcuts, or production changes.
