---
status: pending
priority: p3
issue_id: "004"
tags: [code-review, accessibility, css]
dependencies: []
---

# Header timestamp font-size 0.72rem may be too small for mobile readability

## Problem Statement

The 480px media query sets `.header-timestamp { font-size: 0.72rem }` (~11.5px at default root), which is below the commonly accepted 12px readability floor on mobile. Combined with a pre-existing low-contrast color (`rgba(255,255,255,0.4)` ~2.15:1 ratio against dark header), the timestamp may be difficult to read.

## Findings

- **Source**: Accessibility/UX Reviewer
- **Font-size**: 0.72rem ≈ 11.5px — below 12px readability floor
- **Contrast**: Pre-existing issue, ~2.15:1 ratio vs WCAG 1.4.3 minimum of 4.5:1
- **Note**: The 768px breakpoint uses the same 0.72rem for `.tab-btn`, and the 480px breakpoint actually increases tab font to 0.75rem

## Proposed Solutions

### Option A: Bump timestamp to 0.75rem
```css
.header-timestamp { font-size: 0.75rem; }
```
- **Effort**: Small
- **Risk**: None

## Technical Details

- **Affected files**: `public/index.html` line 1756

## Acceptance Criteria

- [ ] Timestamp font size is at least 0.75rem at 480px
- [ ] Timestamp remains readable on 375px viewport

## Work Log

| Date | Action | Learnings |
|------|--------|-----------|
| 2026-02-28 | Created from PR #2 code review | |

## Resources

- PR: https://github.com/CnxLuc/iran-crisis-monitor/pull/2
