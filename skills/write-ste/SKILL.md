---
name: write-ste
description: Improve the clarity and consistency of technical writing in docs, issues, PR titles and bodies, comments and test explanations while preserving the source language, factual meaning, constraints and protected literals.
---

# Write Clear Technical Prose (STE-inspired)

Use practical clarity principles inspired by ASD-STE100; **this is not formal STE compliance or a certified vocabulary check**.

1. Respect original language and an explicit requested language. Do not translate simply to make text shorter.
2. One principal instruction per sentence where possible; name the actor and action unambiguously. Keep ordered steps ordered and conditions near their corresponding outcomes.
3. Use consistent terms for the same component, environment and status. Distinguish must/should/may, observed/predicted, passing/not run, and confirmed/hypothesized.
4. Prefer precise API operations, observable behavior and accepted error conditions over vague words like "properly", "works" or "obviously".
5. Preserve all protected substrings exactly: code, CLI commands, paths, identifiers, test output, Git SHA, issue links, `Closes`/`Refs` lines, PR template headings, security warnings and disclosure text.
6. Do not invent successful checks, approvals, screenshots or requirements. Recompare revised prose with evidence before publishing.
7. Keep output concise, neutral and appropriate for collaborators. Explain only substantive ambiguity and changes rather than rewriting unrelated text.
