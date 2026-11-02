# Stage contract

A stage is one step of the per-issue pipeline. `$work-issue` runs the stages of one issue in order in one session; a person can also run any stage by invoking its skill directly. `<taskctl>` is the resolved real path of sibling `execute-tasks/scripts/taskctl.py`.

## Pipeline file

The effective pipeline is `<main-checkout>/.agent-workflow/pipeline.json` when present, otherwise the built-in default (`<taskctl> pipeline show`):

| id | skill | gate | access | flags |
| --- | --- | --- | --- | --- |
| `precheck` | `builtin:precheck` | none | read | |
| `plan` | `plan-tasks` | approval | local-write | |
| `execute` | `execute-tasks` | none | local-write | modifies-code, verifies |
| `explain` | `explain-diff` | approval | remote | optional |
| `pr` | `create-pr` | approval | remote | |

Stage fields:

- `id`: unique lowercase name.
- `skill`: a sibling skill directory name, or `builtin:precheck` (a closed issue, an open linked PR, open dependencies or another session's lease stops the issue).
- `gate`: `approval` requires the user's approval in the session before the stage runs or completes; `none` runs without asking.
- `access`: `read` (no writes), `local-write` (worktree and Git metadata only), `remote` (GitHub, Notion or other external writes). Every `remote` stage must have `gate: approval`.
- `modifies-code`: the stage can change tracked files. A later `verifies` stage, or the stage itself, must verify the change before any `remote` stage.
- `verifies`: the stage runs the plan's verification and records evidence.
- `optional`: the stage may be skipped; skipping it does not block later stages.

Add a stage by editing the file, then run `<taskctl> pipeline validate`. Fix every error before the next run. A new stage applies only to stages an issue has not reached; an issue that already passed its position reports it as `skipped_new`.

For one issue only, record a one-off stage instead:

```bash
python3 <taskctl> workspace stage --issue <N> --insert <skill> --after <stage-id> [--id <id>] [--access read|local-write|remote] [--gate approval] [--modifies-code] [--verifies]
```

## Input

Each stage run receives:

- the issue number and repository;
- the issue worktree from `<taskctl> workspace get --issue <N>`;
- the approved plan path (stages after `plan`);
- the lease owner when `$work-issue` already holds the claim.

Run Git with the worktree as the working directory and no options before the subcommand (no `git -C`).

## Result

Every stage ends with one result:

- `done`: the skill finished, the worktree is clean, and the expected artifact exists (the approved plan for `plan`, new commits and current whole-plan verification for `modifies-code`, a PR URL for `pr`);
- `blocked`: the worktree is dirty, an expected artifact is missing, or the skill reported an error (record the reason);
- `needs-approval`: a decision only the user can make is pending.

## Recording progress

After a `done` result, run `<taskctl> workspace stage --issue <N> --complete <stage-id>`. Use `<taskctl> workspace state --issue <N> --set running|blocked|interrupted|done --reason "..."` for the issue's run state, and `<taskctl> pipeline show --issue <N>` for completed stages and `next_stage`.
