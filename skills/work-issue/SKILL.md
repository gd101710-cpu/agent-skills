---
name: work-issue
description: Drive one approved GitHub issue through the stage pipeline (precheck, plan, execute, optional explain, PR) in the current session and terminal, invoking the same unit skills used directly and resuming from recorded progress. One issue per session; run parallel issues in separate terminals. Invoke explicitly.
disable-model-invocation: true
---

# Work Issue — one issue, one session

Usage: `$work-issue <N> [--base <branch>]`. Use `$order-issues` to choose `<N>`.

`<taskctl>` is the resolved real path of sibling `execute-tasks/scripts/taskctl.py`. Read [references/stage-contract.md](references/stage-contract.md) for stage fields and results.

## Authority and limits
- The invocation authorizes the local stages of issue `<N>` only: precheck, its workspace, a planning draft, and execution after the plan is approved. Plan approval and every `approval`-gated or `remote` stage still ask the user in this session. Never merge, close issues, post comments, or touch another issue.
- This session handles one issue. Parallel work means another terminal running `$work-issue` (or a unit skill) for a different issue, in either CLI. Never spawn subagents, background processes, or a second issue.
- Run every skill-backed stage by invoking its skill (`$plan-tasks`, `$execute-tasks`, `$create-pr`, ...) in this session. Never reproduce a skill's steps inline; only `builtin:` stages run as procedure here. If a skill cannot be invoked, block the issue and report.
- The user may interrupt, answer questions, or redirect at any point; follow the user over this procedure, and record the resulting state before stopping.

## Procedure
1. **Pipeline:** run `<taskctl> pipeline validate`. Stop on an error.
2. **Precheck:** read `gh issue view <N> --json state,title,body,url`. Stop when the issue is closed, or an open PR from another branch references it. List open issues named in its `Depends on:` or `Blocked by` lines; if any exist, show them and ask whether to proceed (default: stop and suggest `$order-issues`). In `<taskctl> workspace list`, a lease held by another owner means another session owns the issue: stop and report.
3. **Workspace:** run `<taskctl> workspace get --issue <N> [--base <base>]`, then `workspace claim --issue <N> --owner <owner>` with an ID unique to this session (for example `<cli>:<host>:<start-time>`). Read `<taskctl> pipeline show --issue <N>`; resume at `next_stage` and report completed and skipped stages. Record `--complete precheck` when it is not yet recorded.
4. **Stages:** for each stage from `next_stage`, in order:
   - Set `workspace state --issue <N> --set running`, then invoke the stage skill: `$plan-tasks <issue URL>`, `$execute-tasks <plan path>` (tell it to reuse lease owner `<owner>` and leave the release to this run), `$create-pr` for issue `<N>`, or the configured skill with the issue and plan path.
   - `gate: approval`: the stage's approval happens with the user in this session (`$plan-tasks` asks for plan approval; before `$create-pr`, show branch, head SHA and verification summary and ask). `optional`: ask once whether to run or skip.
   - Derive the result as in the stage contract. `done` → `workspace stage --issue <N> --complete <id>`. `blocked` or `needs-approval` → `workspace state --set blocked --reason "..."`, report what is needed, and stop.
   - Reread `pipeline show --issue <N>` at each stage boundary; a stage added to the pipeline applies from here on.
5. **Finish:** when no stage remains, set `workspace state --set done`. Release the lease with the same owner whenever the run ends, including a block or a user stop. Report completed stages, the PR URL or blocker, and the next action: `$order-issues` to pick the next issue, `$repair-pr` for review or CI, `$cleanup-branch` after merge.

## Interruption
A session that stops without releasing (for example, at a usage limit) leaves its lease and commits in the worktree. To continue in another terminal or CLI, show `<taskctl> workspace list`, release with `workspace release --issue <N> --owner <old-owner> --force` only after the user confirms the old session has stopped, then run `$work-issue <N>` again.
