# Implementation Tasks

Source: https://github.com/g-seo/agent-skills/issues/9
Source revision: 2026-10-27T11:48:03Z
Source digest: sha256:3d960a10e7f0466047021f5e3e30c7246292212b4196b43a3d2c183ee415f495
Plan approval: approved

## T001: Add the `taskctl.py workspace` command table to README
- Depends on: none
- Touches: README.md
- Goal: README has one Korean table listing all seven `workspace` subcommands with purpose and example.
- Scope: a "workspace 명령" subsection after the "병렬 실행" subsection with a one-line lead-in showing `python3 <agent-skills>/skills/execute-tasks/scripts/taskctl.py workspace ...`, and a table (command, purpose, example) for `get`, `list`, `claim`, `release`, `remove`, `stage`, `state`.
- Out of scope: other README sections, `runtimes.md`, `taskctl.py`, `pipeline`/`overlap` tables.
- Acceptance criteria:
  - AC-001: The table has exactly the seven subcommands from `taskctl.py workspace --help`, using only flags the parser accepts.
  - AC-002: Each example's flags parse (`python3 skills/execute-tasks/scripts/taskctl.py workspace <cmd> --help` lists every flag used).
  - AC-003: `git diff --stat` shows only `README.md`, and only the new subsection is added.
- Verification:
  - `python3 skills/execute-tasks/scripts/taskctl.py workspace <cmd> --help` for each of the seven commands — every example flag is listed.
  - `git diff --stat` and `git diff --check` — only README.md, clean.
- Risks / constraints: keep README language (Korean) and style.
