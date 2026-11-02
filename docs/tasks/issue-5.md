# Implementation Tasks

Source: https://github.com/g-seo/agent-skills/issues/5
Source revision: 2026-10-27T11:12:35Z
Source digest: sha256:f770d21052b152f898e86e17d5ef26714bfae6f04990bbb4170ad96e3b2c08ff
Plan approval: approved

## Coverage

| Issue requirement | Task |
| --- | --- |
| `workspace get/list/remove`, registry in git common dir, file lock, `.git/info/exclude`, ignore unregistered worktrees | T001 |
| `claim` / `release` lease, no automatic stale takeover, concurrent registry writes | T002 |
| `- Touches:` in template and parser, `overlap` command | T003 |
| `plan-tasks`, `execute-tasks`, `explain-diff`, `create-pr`, `repair-pr` changes, precheck, shared Git and `taskctl.py` path rules | T004 |
| `cleanup-branch` worktree, branch and registry removal | T005 |
| Codex rules template, `README.md`, `AGENTS.md` | T006 |
| End-to-end two-session check, `codex execpolicy check`, regression suite | T007 |

## T001: Add the per-issue workspace registry and `workspace get/list/remove`
- Depends on: none
- Touches: skills/execute-tasks/scripts/taskctl.py, skills/execute-tasks/tests/test_workspace.py
- Goal: `taskctl.py workspace get --issue N` returns one stable worktree and branch per issue from any checkout of the repository.
- Scope:
  - `workspace get --issue N [--base <branch>] [--branch <name>]`: reuse a registered entry; otherwise fetch the base when a remote exists, create `<main-root>/.worktrees/issue-N` on a new branch (default `fix/issue-N`) from the base, add `.worktrees/` to `info/exclude` in the common dir once, and write the registry entry. Output JSON with `issue`, `worktree`, `branch`, `base`, `plan`, `stages`.
  - Without `--issue`: infer the issue from the current worktree's registry entry; fail with the active candidates when the current checkout maps to none.
  - Registry at `<git-common-dir>/agent-workflow/issues/<N>.json`, written atomically under a lock file in the same directory.
  - `workspace list`: all registry entries with existence and dirty state of each worktree.
  - `workspace remove --issue N`: refuse a dirty or missing-registry worktree; otherwise remove the worktree and the registry entry. Branch deletion is not part of this command.
  - Never modify worktrees that have no registry entry.
- Out of scope: leases (T002), branch deletion (T005), skill text changes.
- Acceptance criteria:
  - AC-001: First `get` creates the worktree and branch; a second `get` from the main checkout and from inside the worktree returns identical JSON without creating anything.
  - AC-002: `get` with an existing branch or path that is not registered fails with a clear error and changes nothing.
  - AC-003: `get` without `--issue` inside a registered worktree returns that entry; in the main checkout it fails and lists active issues.
  - AC-004: `remove` refuses a dirty worktree and an unregistered path; a clean registered worktree is removed with its entry.
  - AC-005: `.worktrees/` appears in `info/exclude` exactly once, and the main checkout stays clean after `get`.
  - AC-006: The per-worktree `progress.json` path and existing commands behave as before.
- Verification:
  - `python3 -m unittest discover -s skills/execute-tasks/tests -p 'test_*.py' -v` — all tests pass, including new workspace tests that use a temporary repository with a local bare remote.
  - `python3 -m py_compile skills/execute-tasks/scripts/taskctl.py` — exit 0.
- Risks / constraints: stdlib only, Python 3.10+. Run Git with `cwd=` set, not `git -C`, to match the Codex prefix rules.

## T002: Add issue leases and safe concurrent registry writes
- Depends on: T001
- Touches: skills/execute-tasks/scripts/taskctl.py, skills/execute-tasks/tests/test_workspace.py
- Goal: two sessions cannot hold the same issue, and parallel registry updates never lose data.
- Scope:
  - `workspace claim --issue N --owner <id>` and `workspace release --issue N --owner <id>`. `claim` fails with the current holder when another owner holds the lease; the same owner can reclaim. `release` by a different owner fails.
  - `workspace list` shows the lease holder and claim time.
  - No automatic takeover of an old lease; the error tells the user to inspect the worktree and release explicitly (`release --force` only with an explicit flag).
  - Lock acquisition with a bounded wait and a clear error on timeout.
- Out of scope: coordinator interruption handling (issue #6).
- Acceptance criteria:
  - AC-007: A second owner's `claim` fails and names the holder; `release` by the holder lets the second owner claim.
  - AC-008: N parallel processes updating different issues and the same issue leave a valid registry with no lost entries.
  - AC-009: A held lock causes a timed-out command to fail without partial writes.
- Verification:
  - `python3 -m unittest discover -s skills/execute-tasks/tests -p 'test_*.py' -v` — lease and multiprocess tests pass.
- Risks / constraints: use `fcntl` file locks (Linux/macOS); document that Windows-native Python is unsupported, as WSL is the supported setup.

## T003: Add `Touches` plan metadata and the `overlap` command
- Depends on: none
- Touches: skills/execute-tasks/scripts/taskctl.py, skills/execute-tasks/tests/test_taskctl.py, skills/plan-tasks/assets/TASKS.template.md
- Goal: approved plans declare touched paths, and `taskctl.py overlap` returns a deterministic parallel or sequential verdict.
- Scope:
  - Parse an optional `- Touches: <glob>, <glob>` line per task (at most one). Missing `Touches` remains valid for existing and NEW PROJECT plans.
  - `overlap --plans <a> <b> ...`: report overlapping glob pairs between plans; return `sequential` when any overlap exists or any task lacks `Touches` (reason `unknown`), else `parallel`. Treat paths a plan marks as shared (`- Touches:` entries prefixed with `shared:`) as overlapping with every other plan.
  - Add `- Touches:` to `TASKS.template.md`.
- Out of scope: requiring `Touches` in `plan-tasks` text (T004).
- Acceptance criteria:
  - AC-010: Plans with disjoint globs → `parallel`; shared file or glob intersection → `sequential` listing the paths.
  - AC-011: A task without `Touches` → `sequential` with reason `unknown`; `validate` still accepts that plan.
  - AC-012: More than one `Touches` line in a task fails validation.
- Verification:
  - `python3 -m unittest discover -s skills/execute-tasks/tests -p 'test_*.py' -v` — new parser and overlap tests pass; existing tests unchanged.
- Risks / constraints: glob intersection is approximate; prefer reporting a false overlap over missing a real one.

## T004: Make issue-scoped skills workspace-aware
- Depends on: T001, T002, T003
- Touches: skills/plan-tasks/SKILL.md, skills/execute-tasks/SKILL.md, skills/execute-tasks/references/task-execution.md, skills/explain-diff/SKILL.md, skills/create-pr/SKILL.md, skills/repair-pr/SKILL.md
- Goal: each issue-scoped skill finds and uses the issue's worktree, whatever directory the session started in.
- Scope:
  - `plan-tasks` (MAINTENANCE): precheck (stop when the issue is closed or an open PR references it); call `workspace get` and write `docs/tasks/issue-<N>.md` inside that worktree; require one `Touches` line per task. State that `workspace get` creates the worktree and branch without switching the current checkout.
  - `execute-tasks`: call `workspace get` and `claim` first and `release` at completion or block; replace "single checkout/branch, no multiple runs" with "no concurrent runs on the same issue or worktree"; use the registered branch; in a delegated non-interactive run, block instead of asking.
  - `explain-diff`, `create-pr`: resolve the worktree with `workspace get`. `repair-pr`: resolve or create the worktree for the PR's issue branch.
  - Shared rules in each changed skill: run Git with the worktree as the working directory, with no options before the subcommand (no `git -C`); call `taskctl.py` by its resolved real path.
  - NEW PROJECT and OSS flows stay unchanged.
- Out of scope: coordinator dispatch (issue #6), `cleanup-branch` (T005).
- Acceptance criteria:
  - AC-013: Each changed `SKILL.md` instructs `workspace get` before reading or writing issue state, and no changed skill uses `git -C` for a write or a symlinked `taskctl.py` path.
  - AC-014: `plan-tasks` text contains the precheck and the `Touches` requirement; `execute-tasks` text contains claim/release and the narrowed concurrency rule.
  - AC-015: NEW PROJECT and OSS instructions are unchanged except for the shared Git rule.
- Verification:
  - `grep -n "git -C" skills/*/SKILL.md` — no write usage remains.
  - `git diff -- skills/` reviewed against AC-013..AC-015.
  - `python3 -m unittest discover -s skills/execute-tasks/tests -p 'test_*.py' -v` — still passes.
- Risks / constraints: keep the text concise and identical across CLIs; name sibling skills as `$skill-name`.

## T005: Remove merged issue worktrees in `cleanup-branch`
- Depends on: T001
- Touches: skills/cleanup-branch/SKILL.md
- Goal: cleanup of a merged issue also removes its worktree and registry entry.
- Scope:
  - Before deleting a verified merged branch, if a registered worktree holds it, run `workspace remove`; a dirty worktree is preserved and reported, and its branch is kept.
  - Remove the registry entry after the branch is deleted. Leave unregistered worktrees untouched, as today.
- Out of scope: other cleanup rules.
- Acceptance criteria:
  - AC-016: The skill text orders worktree removal before branch deletion and preserves dirty worktrees.
  - AC-017: Unregistered worktree handling is unchanged.
- Verification:
  - `git diff -- skills/cleanup-branch/SKILL.md` reviewed against AC-016..AC-017.
- Risks / constraints: none beyond T001.

## T006: Add the Codex rules template and update repository docs
- Depends on: T004, T005
- Touches: templates/codex/agent-workflow.rules, README.md, AGENTS.md
- Goal: users can set up Codex and Claude Code for single and parallel use from the README.
- Scope:
  - `templates/codex/agent-workflow.rules`: allow `git add|commit|worktree|branch|switch|fetch|rebase|merge` and `python3 <repo>/skills/execute-tasks/scripts/taskctl.py`; forbid `git push`.
  - `README.md`: workspace model, single use and two-terminal parallel use, Codex setup (start from the repository root, install the rules file by symlink into `~/.codex/rules/`), residual risks (hooks run outside the sandbox, remote writes controlled by skill policy), updated introduction.
  - `AGENTS.md`: one issue = one worktree = one unit skill run; parallelism is only the number of concurrent runs; shared Git and `taskctl.py` path rules.
- Out of scope: changing the user's Codex or Claude Code configuration.
- Acceptance criteria:
  - AC-018: `codex execpolicy check --rules templates/codex/agent-workflow.rules` returns allow for the eight Git subcommands and `taskctl.py`, and forbidden for `git push`.
  - AC-019: README and AGENTS.md describe the items above without CLI-specific paths in shared rules.
- Verification:
  - `codex execpolicy check --rules templates/codex/agent-workflow.rules -- git commit -m x` and the same for each allowed command and `git push` — expected decisions.
- Risks / constraints: the rules file contains this checkout's absolute path for `taskctl.py`; document how to adjust it.

## T007: Verify two concurrent sessions end to end
- Depends on: T006
- Touches: skills/execute-tasks/tests/test_workspace_integration.py
- Goal: confirm the issue's acceptance criteria hold for two sessions on two issues.
- Scope:
  - Automated integration test: in a temporary repository with a bare remote, two processes each run `workspace get` + `claim`, `init`, a task commit and `complete` for different issues at the same time; a third process's `claim` on a held issue fails.
  - Manual check with the user: one Claude Code terminal and one Codex terminal (started from the repository root, rules installed) each run `$execute-tasks` on a scratch issue plan; record results in the final evidence.
- Out of scope: PR creation on GitHub.
- Acceptance criteria:
  - AC-020: The integration test passes and both ledgers are complete and independent.
  - AC-021: The Codex session creates its worktree and commits without approval prompts; the Claude Code session completes the same steps.
- Verification:
  - `python3 -m unittest discover -s skills/execute-tasks/tests -p 'test_*.py' -v` — all tests pass.
  - `python3 -m py_compile skills/execute-tasks/scripts/taskctl.py` — exit 0.
  - Manual two-terminal run — results recorded as evidence; if not performed, recorded as a limitation.
- Risks / constraints: AC-021 needs the user to run the Codex terminal.
