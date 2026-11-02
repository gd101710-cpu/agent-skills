# Implementation Tasks

Source: https://github.com/g-seo/agent-skills/issues/6
Source revision: 2026-10-27T11:12:43Z
Source digest: sha256:94799f94332d2e5ce797208c28d21c9cfb18ad1c949b9e9ad14ffc81a6a05624
Plan approval: approved

## Planning decisions

- Pipeline file: `.agent-workflow/pipeline.json` in the target repository's main checkout. `taskctl.py` is stdlib-only and Python has no YAML parser in the standard library. The issue's `pipeline.yaml` name is replaced by JSON with the same fields.
- Skill name: `work-issues`.
- Verification after code changes: a stage declares `verifies: true` when it runs the plan's verification (the default `execute` stage does). `pipeline validate` requires every `modifies-code` stage to be followed by a verifying stage, or to verify itself, before any `remote` stage.
- Preflight is a skill procedure, not a `taskctl.py` command: `taskctl.py` already runs Git outside the Codex sandbox through the rules file, so only Git commands run by the agent itself prove that worker commits will succeed.

## Coverage

| Issue requirement | Task |
| --- | --- |
| Default pipeline, pipeline file loading, concurrency resolution, `pipeline validate` | T001 |
| Completed stages per issue, one-off stages, run state (`interrupted` etc.), resume from registry | T002 |
| `references/stage-contract.md`, `references/runtimes.md` (subagent, process, fallback, Codex escalation) | T003 |
| `work-issues` skill: flow, precheck, batched approvals, overlap handling, slot scheduling, preflight, interruption | T004 |
| `execute-tasks` delegated runs, `AGENTS.md`, `README.md`, symlinks | T005 |
| Two-issue end-to-end checks and runner checks | T006 |

## T001: Add the stage pipeline model and `pipeline show/validate`
- Depends on: none
- Touches: skills/execute-tasks/scripts/taskctl.py, skills/execute-tasks/tests/test_pipeline.py
- Goal: `taskctl.py` returns the effective stage pipeline and concurrency for a repository and rejects unsafe pipelines.
- Scope:
  - Built-in default pipeline: `precheck` (built-in, `read`), `plan` (`plan-tasks`, gate `approval`, `local-write`), `execute` (`execute-tasks`, `local-write`, `modifies-code`, `verifies`, parallel), `explain` (`explain-diff`, optional, `remote` with gate), `pr` (`create-pr`, gate `approval`, `remote`). Default `concurrency` 2.
  - Stage fields: `id`, `skill` (sibling skill name or `builtin:precheck`), `mode` (`per-issue`), `gate` (`none` | `approval`), `access` (`read` | `local-write` | `remote`), `modifies-code`, `verifies`, `optional`, `parallel`.
  - `pipeline show [--concurrency K]`: load `<main-root>/.agent-workflow/pipeline.json` when present, else the default; resolve concurrency from the flag, then the file, then 2; output stages and concurrency.
  - `pipeline validate [--file <path>]`: unique stage IDs; each skill exists as `skills/<name>/SKILL.md` next to the running `taskctl.py`, or is a known built-in; valid enum values; `remote` stages have gate `approval`; every `modifies-code` stage is verified before any later `remote` stage; concurrency is a positive integer.
- Out of scope: per-issue progress (T002), skill text.
- Acceptance criteria:
  - AC-001: Without a pipeline file, `pipeline show` returns the default stages and concurrency 2; `--concurrency 1` overrides it; a file value applies when the flag is absent.
  - AC-002: `pipeline validate` rejects a missing skill, an invalid `access`, an ungated `remote` stage, an unverified `modifies-code` stage before a `remote` stage, duplicate IDs, and a non-positive concurrency, each with a specific error.
  - AC-003: The default pipeline passes `pipeline validate`.
  - AC-004: Invalid JSON in the pipeline file fails with the file path.
- Verification:
  - `python3 -m unittest discover -s skills/execute-tasks/tests -p 'test_*.py' -v` — all tests pass, including new pipeline tests.
  - `python3 -m py_compile skills/execute-tasks/scripts/taskctl.py` — exit 0.
- Risks / constraints: stdlib only; keep existing commands unchanged.

## T002: Record stage progress, one-off stages and run state per issue
- Depends on: T001
- Touches: skills/execute-tasks/scripts/taskctl.py, skills/execute-tasks/tests/test_pipeline.py
- Goal: a coordinator can stop at any point and resume from the registry without rerunning completed stages.
- Scope:
  - `workspace stage --issue N --complete <stage-id>`: append to the entry's `stages` once, in pipeline order; reject unknown stages and completing a stage before its predecessors.
  - `workspace stage --issue N --insert <skill> --after <stage-id> [--access ...] [--modifies-code]`: add a one-off stage for that issue only, stored in the entry; it must pass the same validation rules.
  - `workspace state --issue N --set pending|running|blocked|interrupted|done [--reason ...]`.
  - `pipeline show --issue N`: the effective pipeline for that issue (file or default plus its one-off stages), completed stages, `next_stage` and state. Stages added to the file after an issue completed later stages are reported as `skipped_new` and not scheduled retroactively.
  - Registry entries without these fields (created before this change) are treated as not started.
- Out of scope: dispatching workers.
- Acceptance criteria:
  - AC-005: Completing stages in order updates `next_stage`; completing out of order or an unknown stage fails without changing the entry.
  - AC-006: A one-off stage appears only in that issue's `pipeline show --issue` output, in the requested position.
  - AC-007: Editing the pipeline file between calls changes only the remaining stages; a new stage inserted before a completed stage is reported as `skipped_new`.
  - AC-008: `workspace state` persists the state and reason and shows them in `workspace list`; legacy entries show state `pending`.
- Verification:
  - `python3 -m unittest discover -s skills/execute-tasks/tests -p 'test_*.py' -v` — all tests pass.
- Risks / constraints: all writes use the registry lock from issue #5.

## T003: Write the stage contract and runner references
- Depends on: T002
- Touches: skills/work-issues/references/stage-contract.md, skills/work-issues/references/runtimes.md
- Goal: any skill author or coordinator session knows how a stage receives work and reports results, and how each CLI starts workers.
- Scope:
  - `stage-contract.md`: input (issue, worktree, plan path, non-interactive flag), JSON receipt (`status`: `done` | `blocked` | `needs-approval`, `summary`, `head_sha`), meaning of `access`, `gate`, `modifies-code`, `verifies`; wrapping skills without receipt support by deriving the result from Git state; how to add a stage to `.agent-workflow/pipeline.json` and check it with `pipeline validate`.
  - `runtimes.md`: `subagent` runner (Claude Code Agent tool without CLI-managed worktree isolation; Codex subagents), `process` runner (`claude -p`, `codex exec` started from the worker's repository root), fallback from a failing Codex subagent to `process`, Codex escalation when starting `codex exec` from Codex, shared versus separate usage limits, and a results table for verified and unverified combinations (Codex subagent creation failed inside `codex exec`; TUI unverified).
- Out of scope: the coordinator procedure (T004).
- Acceptance criteria:
  - AC-009: Both files exist, use only commands that exist in `taskctl.py`, and name sibling skills as `$skill-name`.
  - AC-010: `runtimes.md` records the known Codex subagent failure and marks unverified combinations explicitly.
- Verification:
  - `grep -o 'taskctl.py [a-z-]* [a-z-]*' skills/work-issues/references/*.md` — every command matches a `taskctl.py --help` subcommand.
  - `git diff --check` — clean.
- Risks / constraints: CLI-specific details stay in `runtimes.md` only.

## T004: Add the `work-issues` coordinator skill
- Depends on: T003
- Touches: skills/work-issues/SKILL.md, skills/work-issues/agents/openai.yaml
- Goal: one explicit invocation runs several issues through the pipeline with batched approvals, one issue at a time or concurrently.
- Scope:
  - Frontmatter with `name`, `description`, `disable-model-invocation: true`; `agents/openai.yaml` with implicit invocation disabled.
  - Usage `$work-issues <issue>... [--concurrency K] [--runner subagent|process]`.
  - Procedure: `pipeline validate`; preflight (create and delete a temporary branch with `git branch` run directly by the agent, and run `taskctl.py workspace list`; on failure, stop with setup guidance and dispatch nothing); per issue precheck, `workspace get`, `plan-tasks`; one batched approval screen with plan summaries and the `overlap` verdict; schedule dependency-ready issues into free slots up to the resolved concurrency; record stage completion and run state through `taskctl.py`; reread the pipeline at each stage boundary; one batched PR approval, then `$create-pr` per issue.
  - Overlapping issues run sequentially; the later issue waits for the earlier PR to merge and is updated with `$repair-pr`.
  - A worker that ends without a receipt is marked `interrupted`; check its worktree, release its lease after confirmation, and resume or reassign. Other workers continue.
  - The coordinator never implements code, pushes, creates PRs or merges without the batched approval; it does not poll in the background.
- Out of scope: `add-stage` helper, automatic merge, adaptive concurrency.
- Acceptance criteria:
  - AC-011: The skill text covers each procedure step above and refers to `references/stage-contract.md` and `references/runtimes.md` for details.
  - AC-012: Concurrency 1 is described as the single-agent workflow with the same stages; direct unit-skill invocation remains valid.
  - AC-013: Approval gates and the no-remote-write-before-approval rule are explicit.
- Verification:
  - Review `git diff -- skills/work-issues/` against AC-011..AC-013.
  - `python3 -c` frontmatter check: `name` and `description` present, `disable-model-invocation: true`.
- Risks / constraints: keep the skill concise; CLI-specific steps only in `runtimes.md`.

## T005: Allow delegated runs and document the coordinator
- Depends on: T004
- Touches: skills/execute-tasks/SKILL.md, AGENTS.md, README.md
- Goal: unit skills accept coordinator-dispatched work, and users can find and use `work-issues`.
- Scope:
  - `execute-tasks`: one coordinator-dispatched worker per issue is allowed; the worker still must not spawn subagents itself.
  - `AGENTS.md`: issue-scoped skills follow `skills/work-issues/references/stage-contract.md`; new stages are checked with `pipeline validate`.
  - `README.md`: skill table entry, usage examples for single and concurrent runs, runner matrix (manual, subagent, process; shared versus separate limits), `.agent-workflow/pipeline.json` example.
  - Create `~/.agents/skills/work-issues` and `~/.claude/skills/work-issues` symlinks to the main checkout's `skills/work-issues` without overwriting existing entries.
- Out of scope: changes to other skills.
- Acceptance criteria:
  - AC-014: The `execute-tasks` rule distinguishes a coordinator-dispatched worker from self-spawned subagents.
  - AC-015: README and AGENTS.md describe the items above; both symlinks resolve to `skills/work-issues` in the main checkout.
- Verification:
  - `ls -l ~/.agents/skills/work-issues ~/.claude/skills/work-issues` — symlinks resolve (the target exists after the PR is merged into the main checkout).
  - `git diff --check` — clean.
- Risks / constraints: the symlink target exists in the main checkout only after merge; record that as expected.

## T006: Verify two-issue runs end to end
- Depends on: T005
- Touches: skills/execute-tasks/tests/test_pipeline_integration.py, skills/work-issues/references/runtimes.md
- Goal: confirm the issue's acceptance criteria for coordinator state handling and runners.
- Scope:
  - Automated test: in a temporary repository with a bare remote, simulate two issues through `pipeline show --issue`, `workspace stage --complete`, `workspace state` with concurrency 1 and 2, an interrupted worker, a pipeline file edit mid-run, and a one-off stage.
  - Manual runs with the user: Claude Code `subagent` two-issue run; Codex `process` two-issue run; mixed `process` run (`claude -p` + `codex exec`); Codex TUI subagent commit test. Record results in `runtimes.md`.
- Out of scope: GitHub PR creation in tests.
- Acceptance criteria:
  - AC-016: The automated test passes and covers AC-005..AC-008 in one flow for two issues.
  - AC-017: Manual run results, or their absence, are recorded in `runtimes.md`.
- Verification:
  - `python3 -m unittest discover -s skills/execute-tasks/tests -p 'test_*.py' -v` — all tests pass.
  - `python3 -m py_compile skills/execute-tasks/scripts/taskctl.py` — exit 0.
- Risks / constraints: manual runs need the user's Codex and Claude Code sessions; unperformed runs are recorded as limitations.
