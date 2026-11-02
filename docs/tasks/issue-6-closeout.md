# Implementation Tasks

Source: https://github.com/g-seo/agent-skills/issues/6
Source revision: 2026-10-27T11:12:43Z
Source digest: sha256:94799f94332d2e5ce797208c28d21c9cfb18ad1c949b9e9ad14ffc81a6a05624
Plan approval: approved

## Context

The first plan for this issue (`docs/tasks/issue-6.md`, PR #8) is complete. This close-out plan covers the remaining work found by the `$work-issues #9 #10` run (PRs #11 and #12).

- The coordinator performed the `plan-tasks` and `create-pr` steps itself instead of invoking those skills, and the worker handoff carried implementation instructions. The issue requires the handoff to contain only the unit-skill invocation, the non-interactive flag and paths.
- The run verified Claude Code subagent workers committing in registered worktrees and two concurrent workers.

User decision (option A): the acceptance criterion "Claude Code `subagent` runner and Codex `process` runner each complete a two-issue run" is closed with the Codex runs recorded as unverified. Codex runner verification moves to a separate issue.

## T001: Make the coordinator invoke unit skills and keep handoffs minimal
- Depends on: none
- Touches: skills/work-issues/SKILL.md, skills/work-issues/references/runtimes.md
- Goal: `$work-issues` runs every skill-backed stage through the skill itself, and worker handoffs carry no implementation instructions.
- Scope:
  - `SKILL.md`: add a rule that each skill-backed stage (`plan`, `pr`, `explain` and added stages) is run by invoking that skill (`$plan-tasks`, `$create-pr`, ...). The coordinator does not reproduce a skill's steps inline; only `builtin:` stages run as coordinator procedure. If a skill cannot be invoked, block the issue and report it.
  - `SKILL.md`: state that the worker handoff follows `runtimes.md` exactly. Task content comes from the approved plan, never from the handoff.
  - `runtimes.md` Handoff section: add an explicit "do not add implementation instructions, file locations or content guidance" rule and state that the worker reads the plan.
- Out of scope: `taskctl.py`, other skills, the verified-combinations table (T002).
- Acceptance criteria:
  - AC-001: `SKILL.md` contains the skill-invocation rule for skill-backed stages and the builtin-stage exception.
  - AC-002: `SKILL.md` and `runtimes.md` both state that handoffs contain no implementation instructions.
  - AC-003: Procedure steps 4 and 9 still name `$plan-tasks` and `$create-pr` and are consistent with the new rule.
- Verification:
  - `grep -n "invok" skills/work-issues/SKILL.md` and `grep -n "implementation instructions" skills/work-issues/SKILL.md skills/work-issues/references/runtimes.md` — rules present.
  - `git diff --check` — clean.
- Risks / constraints: keep `SKILL.md` concise; CLI-specific invocation details stay in `runtimes.md`.

## T002: Record verified runner combinations
- Depends on: T001
- Touches: skills/work-issues/references/runtimes.md
- Goal: the "Verified combinations" table reflects the `$work-issues #9 #10` run.
- Scope:
  - Mark "Claude Code Agent-tool worker committing in a registered worktree" as Verified with evidence (issues #9 and #10, PRs #11 and #12).
  - Add a Verified row for two concurrent Claude Code subagent workers sharing one registry (same evidence).
  - Keep Codex TUI subagent and mixed `process` rows Unverified; add an Unverified row for a Codex `process` two-issue run, noting that verification is tracked separately.
  - Replace the closing note that says only automated tests were run.
- Out of scope: running new Codex checks; creating the follow-up issue.
- Acceptance criteria:
  - AC-004: The table has the two Verified Claude rows with PR references and the Codex rows marked Unverified.
  - AC-005: No other section of `runtimes.md` changes except the closing note.
- Verification:
  - `gh pr view 11 --repo g-seo/agent-skills --json state` and `gh pr view 12 ...` — both MERGED (evidence exists).
  - `git diff --check` — clean.
- Risks / constraints: record only what the run actually showed.
