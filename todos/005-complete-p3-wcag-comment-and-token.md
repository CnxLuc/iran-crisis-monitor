---
status: pending
priority: p3
issue_id: "005"
tags: [code-review, css, documentation]
dependencies: []
---

# Add WCAG reference to 44px touch target comment and consider CSS token

## Problem Statement

The `44px` min-height value appears twice (`.site-header` and `.tab-btn`) as a magic number. It follows WCAG 2.5.8 (Target Size Minimum) and Apple HIG, but the comment only says "larger touch targets" without citing the standard. A CSS custom property would make the intent self-documenting.

## Findings

- **Source**: Code Quality/Pattern Recognition Specialist
- **Location**: Lines 1749, 1766 in the 480px media query

## Proposed Solutions

### Option A: Add comment + optional token
```css
/* Touch target minimum per WCAG 2.5.8 / Apple HIG */
--touch-target-min: 44px;
```
- **Effort**: Small
- **Risk**: None

## Acceptance Criteria

- [ ] Comment references WCAG 2.5.8
- [ ] 44px value is either documented or extracted to a CSS custom property

## Work Log

| Date | Action | Learnings |
|------|--------|-----------|
| 2026-02-28 | Created from PR #2 code review | |

## Resources

- PR: https://github.com/CnxLuc/iran-crisis-monitor/pull/2
- WCAG 2.5.8: https://www.w3.org/WAI/WCAG21/Understanding/target-size.html
