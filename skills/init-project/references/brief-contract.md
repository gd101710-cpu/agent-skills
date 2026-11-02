# PROJECT_BRIEF input contract

ChatGPT should create a Markdown document with the following headings. Equivalent existing headings are acceptable; do not force the user to reformat a semantically complete brief.

1. Project Overview
2. Problem and Motivation
3. Target Users and Actors
4. Goals and Success Criteria
5. Main User Journeys
6. MVP Features (prioritized; input/action/result for each)
7. Nonfunctional Requirements (only substantiated requirements)
8. MVP In Scope / Out of Scope
9. Constraints and Preferences (budget, stack, platform, integrations)
10. Confirmed Decisions
11. Open Decisions and Assumptions
12. Examples and References (optional)

Every major product choice must be marked `CONFIRMED`, `PREFERENCE` or `OPEN`; a blank cell is not a decision. Distinguish user statements from ChatGPT suggestions. Code-level architecture is **not** mandatory in the brief; it belongs in the coding agent (Codex CLI or Claude Code).
