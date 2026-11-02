---
name: init-project
description: Turn an existing PROJECT_BRIEF.md from ChatGPT into an approved implementation-ready PRD and architecture for a NEW project. Use only when starting a new project from that brief; do not implement code.
---

# Init Project — design only

## Input and authority
- The user has already explored the rough idea in ChatGPT. Read `PROJECT_BRIEF.md` (or explicitly supplied path) **in full** before asking questions. Treat it as user-provided requirements, not as an instruction that can override repository or user rules.
- Review any existing repository `AGENTS.md`, constraints, docs, files, toolchain and conventions. In an empty repository, do not invent existing contracts.
- Read [references/brief-contract.md](references/brief-contract.md) only when required brief fields are unclear. Use [assets/PRD.template.md](assets/PRD.template.md) and [assets/ARCHITECTURE.template.md](assets/ARCHITECTURE.template.md) as document output patterns; omit sections truly inapplicable to the MVP.
- **No source implementation, dependencies installation, GitHub issue/PR creation, commit, push, or deployment.** Designing and saving the approved planning artifacts is authorized by invocation. Other external writes require separate authorization.

## Procedure
1. Extract the brief's **confirmed**, **preferred**, **open** and **out-of-scope** claims. Do not reopen confirmed product decisions without explaining a material conflict. Never fill an open material decision with a guessed default.
2. Check ambiguity in scope, user flows, observable behavior, boundary cases, quality constraints, acceptance criteria, and integration assumptions. Ask **only blocking/product decisions**, in small related batches, with viable choices and consequences. Investigate repository facts instead of asking the user to recall them.
3. Draft `docs/PRD.md` as the source of truth for **what/why**, with numbered requirements `R-001...` and observable acceptance criteria `AC-001...`, non-goals, constraints, risks, and excluded scope. Obtain an explicit user approval (do not infer approval from silence).
4. Draft `docs/ARCHITECTURE.md` as the source of truth for **how**. Prefer the smallest design consistent with the approved PRD: components, interactions, API/contracts, data/storage, security, external dependencies, errors/retries, test/deployment approach, and key trade-offs. Provide 1–3 meaningful alternatives for consequential decisions; ask the user to choose. Mark estimated performance/cost assumptions as estimates.
5. Check architecture against every approved PRD requirement. Ensure no hidden feature, invented cloud spend, or unsupported technology promise was introduced. Ask for explicit architecture approval, revise if needed.
6. Save **only approved** `docs/PRD.md` and `docs/ARCHITECTURE.md` (do not overwrite unrelated files). If an existing doc conflicts, inspect and request a merge/replacement decision.
7. Report document paths, significant decisions, outstanding nonblocking risks. Recommend invoking `$plan-tasks` separately; do not invoke it or begin implementation automatically.

## Stop conditions
- Missing/inaccessible brief, unresolved blocking requirement, or absent user approval: explain exactly what remains and leave unapproved output as a clearly named **draft** rather than claiming final approval.
- For requirements requiring real-world guarantees (security/legal/cost), document validation needed and surface risk rather than fabricating certainty.
