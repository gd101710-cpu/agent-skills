# Repository Guidelines

## Skill Structure
- Store skills in `skills/<skill-name>/` using lowercase `kebab-case`.
- Every skill must contain `SKILL.md` with `name` and `description` frontmatter.
- Keep each skill focused on one reusable workflow.
- Keep instructions concise and actionable.
- Use `scripts/` for reusable automation, `references/` for documentation, and `assets/` for resources when needed.

## Skill Management
- Prefer a skill-creator skill when creating or substantially updating skills (`$skill-creator` in Codex CLI; use an equivalent when available in Claude Code).
- Treat `skills/` as the single source of truth.
- Manage global skills through per-skill symlinks in `~/.agents/skills/` (Codex CLI) and `~/.claude/skills/` (Claude Code).
- Add or remove symlinks in both locations when skills are created, deleted, or renamed.
- Never overwrite existing skills without authorization.
- Validate and test skills before committing.

## Cross-CLI Compatibility
- Keep each workflow identical in Codex CLI and Claude Code. Codex invokes a skill as `$skill-name`; Claude Code invokes it as `/skill-name`. Skill text uses `$skill-name` to name sibling skills.
- Do not hard-code one CLI's install path, tool name, or session model in shared instructions. Resolve bundled files relative to the loaded `SKILL.md`.
- Use platform-specific settings only when behavior cannot be shared, such as `agents/openai.yaml` (Codex) and Claude-only frontmatter like `disable-model-invocation`. Keep matching policies in both.
- `CLAUDE.md` imports this file; edit rules here only.

## Single and Parallel Execution
- One issue = one worktree = one session in one terminal. Parallelism means more terminals (Codex CLI, Claude Code, or both), each running a different issue; skills never spawn subagents or worker processes for other issues.
- Keep each skill light: `$order-issues` only reports dependency order, `$work-issue` only chains the unit skills for one issue, and unit skills stay usable on their own.
- Issue-scoped skills resolve their location with `taskctl.py workspace get` instead of the current checkout or branch.
- Run Git with the target worktree as the working directory and no options before the subcommand (no `git -C`). Call `taskctl.py` by its resolved real path. Codex allowlist rules in `templates/codex/agent-workflow.rules` match exact command prefixes.
- Issue-scoped skills follow the stage contract in `skills/work-issue/references/stage-contract.md`: they work in the issue worktree and end with a stage result (`done`, `blocked` or `needs-approval`). Check new or changed pipeline stages with `taskctl.py pipeline validate`.

## Git & Security
- Update `README.md` when adding, removing, or renaming skills.
- Commit small, verified changes with descriptive messages.
- Never commit secrets, credentials, `.env` files, or sensitive data.
- Do not push to GitHub unless explicitly requested.