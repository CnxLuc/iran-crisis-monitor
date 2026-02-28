---
status: pending
priority: p2
issue_id: "002"
tags: [code-review, css, dead-code]
dependencies: []
---

# Dead CSS `order` declarations on `.header-logo` and `.header-right`

## Problem Statement

The 480px media query sets `order: 1` on `.header-logo` and `order: 2; margin-left: auto` on `.header-right`. However, `.header-logo` is a grandchild of `.site-header` (nested inside `.header-brand`), not a direct flex child. CSS `order` only affects direct children of a flex container, so these declarations have no effect and imply a reordering that isn't happening.

The `margin-left: auto` on `.header-right` is also redundant since `.site-header` already has `justify-content: space-between`.

## Findings

- **Source**: Code Simplicity Reviewer, Accessibility/UX Reviewer (2/7 agents flagged)
- **Location**: `public/index.html` lines 1754-1755 within the 480px media query
- **Evidence**: DOM structure is `header.site-header > div.header-brand > div.header-logo` — `.header-logo` is not a direct flex child
- **Impact**: 3 lines of CSS noise that misleads future maintainers into thinking elements are being reordered

## Proposed Solutions

### Option A: Remove the dead declarations
```css
/* Remove these three lines from the 480px media query: */
/* .header-logo { order: 1; } */
/* .header-right { order: 2; margin-left: auto; } */
```
- **Pros**: Removes misleading code, simpler diff
- **Cons**: None
- **Effort**: Small (delete 3 lines)
- **Risk**: None

### Option B: Fix to target correct elements
```css
.header-brand { order: 1; }
.header-right { order: 2; }
```
- **Pros**: Actually applies ordering if needed in the future
- **Cons**: Unnecessary since source order is already correct
- **Effort**: Small
- **Risk**: None

## Recommended Action

<!-- Fill during triage -->

## Technical Details

- **Affected files**: `public/index.html`
- **Lines**: 1754-1755

## Acceptance Criteria

- [ ] Dead `order` declarations removed
- [ ] Header layout on mobile unchanged (visual regression check)
- [ ] Desktop layout unchanged

## Work Log

| Date | Action | Learnings |
|------|--------|-----------|
| 2026-02-28 | Created from PR #2 code review | CSS `order` only applies to direct flex children |

## Resources

- PR: https://github.com/CnxLuc/iran-crisis-monitor/pull/2
