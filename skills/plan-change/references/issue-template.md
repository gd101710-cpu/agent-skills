# GitHub Issue Template

Use the target repository's issue template and title convention when present. Use this fallback only when the repository does not define them. Omit a section only when it is genuinely inapplicable, and state `None` where an empty section could hide an unresolved decision.

## Title

Prefer the repository's required format. Otherwise, write a concise, outcome-focused title:

```text
<area>: <desired change>
```

Use an established component name for `<area>` when one exists. Do not invent a prefix solely to fit this pattern.

## Body

```markdown
## Summary
Describe the problem and the intended outcome in one or two short paragraphs.

## Current Behavior and Evidence
- Observed behavior:
- Expected behavior:
- Evidence or reproduction:
- Affected revision:
- Affected users or systems:

## Root Cause
State the confirmed cause and supporting evidence. If it is not confirmed, label the explanation as an assumption and identify what remains unknown.

## Proposed Solution
Describe the agreed implementation approach, affected interfaces or components, important edge cases, and behavior that must remain unchanged.

## Scope
### In Scope
- ...

### Out of Scope
- ...

## Acceptance Criteria
- [ ] ...
- [ ] ...

## Verification
- Automated tests:
- Manual or integration checks:
- Regression coverage:

## Delivery Considerations
- Documentation:
- Data or schema migration:
- Rollout and rollback:
- Observability or operational impact:

## Dependencies
- Depends on: <#N, #M for issues that must be merged first, or none>
- Related (no ordering):
- Follow-up work:
```

## Drafting Checklist

Before presenting the issue for approval, verify that:

- The title and body follow the target repository's conventions, or this fallback when none exist.
- Every claim about current behavior or root cause is supported by evidence or clearly marked as an assumption.
- The proposed solution matches the approach approved by the user and does not include unrelated improvements.
- Acceptance criteria describe observable outcomes, including relevant error and edge-case behavior.
- Verification covers the change and the preserved behavior most at risk of regression.
- Documentation, migration, rollout, rollback, and operational effects are addressed or marked `None`.
- The `- Depends on:` line lists only hard prerequisites as `#N` references (or `none`), so `$order-issues` can parse it.
- Labels, assignees, milestones, projects, and other metadata are not added unless the user requested them or the repository requires them.
