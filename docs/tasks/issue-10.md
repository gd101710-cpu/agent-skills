# Implementation Tasks

Source: https://github.com/g-seo/agent-skills/issues/10
Source revision: 2026-10-27T11:48:04Z
Source digest: sha256:9d10fc6bab59706b687c2812d611f812183358bf315ec386a06ee2866b2a2380
Plan approval: approved

## T001: Add a Codex setup checklist to runtimes.md
- Depends on: none
- Touches: skills/work-issues/references/runtimes.md
- Goal: `runtimes.md` has an ordered Codex setup checklist with one check per item.
- Scope: a "Codex setup checklist" section before "Verified combinations", in English, with five items: rules file present and generated from the current checkout; `codex execpolicy check` returns `allow` for `git commit` and `forbidden` for `git push`; Codex started in the repository root; temporary branch create/delete in the main checkout; one approval per `codex exec` worker started from Codex.
- Out of scope: README, rules template, Codex config, `$work-issues` procedure, the "Verified combinations" table.
- Acceptance criteria:
  - AC-001: The section lists the five items, each with a concrete command or observable result.
  - AC-002: Every command in the checklist runs as written on this machine (rules installed) with the expected result.
  - AC-003: `git diff --stat` shows only `runtimes.md`.
- Verification:
  - Run each checklist command locally — expected results observed.
  - `git diff --stat` and `git diff --check` — only runtimes.md, clean.
- Risks / constraints: keep the file in English; no CLI install paths beyond those already documented.
