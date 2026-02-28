---
status: pending
priority: p2
issue_id: "001"
tags: [code-review, css, mobile, bug]
dependencies: []
---

# Sticky tab-nav `top: 60px` not updated for dynamic header height at 480px

## Problem Statement

The PR changes `.site-header` to `height: auto; min-height: 44px; flex-wrap: wrap` at the 480px breakpoint, making the header height dynamic. However, `.tab-nav` has `position: sticky; top: 60px` (line 270) which assumes a fixed 60px header height. When the header wraps to two lines on narrow screens (~88px), the tab navigation bar will overlap the bottom of the header by ~28px.

This is a **bug introduced by this PR** — the header height is now variable but the sticky offset is still hardcoded.

## Findings

- **Source**: Performance Oracle, Architecture Strategist, Accessibility/UX reviewer (3/7 agents flagged this independently)
- **Location**: `public/index.html` line 270 (`.tab-nav { top: 60px }`) vs lines 1747-1753 (480px header override)
- **Evidence**: Base header is `height: 60px` (line 167). At 480px, header becomes `height: auto; flex-wrap: wrap`. Tab nav sticky offset remains 60px.
- **Impact**: On phones < 480px wide where the header wraps, tabs will visually overlap or tuck under the header when scrolling

## Proposed Solutions

### Option A: Make tab-nav non-sticky at 480px
```css
@media (max-width: 480px) {
  .tab-nav { position: relative; top: auto; }
}
```
- **Pros**: Simple, no JS needed, eliminates the offset problem entirely
- **Cons**: Tabs scroll away on mobile (may be acceptable for a dashboard)
- **Effort**: Small
- **Risk**: Low

### Option B: Use JavaScript to dynamically set tab-nav offset
```javascript
const header = document.querySelector('.site-header');
const tabNav = document.querySelector('.tab-nav');
const ro = new ResizeObserver(() => {
  tabNav.style.top = header.offsetHeight + 'px';
});
ro.observe(header);
```
- **Pros**: Accurate offset at all sizes, preserves sticky behavior
- **Cons**: Adds JS complexity, ResizeObserver dependency
- **Effort**: Small-Medium
- **Risk**: Low

### Option C: Set a reasonable fixed offset at 480px
```css
@media (max-width: 480px) {
  .tab-nav { top: 44px; }
}
```
- **Pros**: Simple CSS fix, works when header doesn't wrap
- **Cons**: Still incorrect if header wraps to 2+ lines; hardcodes another magic number
- **Effort**: Small
- **Risk**: Medium (partially fixes but may still overlap)

## Recommended Action

<!-- Fill during triage -->

## Technical Details

- **Affected files**: `public/index.html`
- **Components**: `.site-header`, `.tab-nav`
- **Lines**: 167 (header height), 270 (tab-nav top), 1747-1753 (480px header override)

## Acceptance Criteria

- [ ] On 375px viewport, scrolling with a wrapped header does not cause tab-nav overlap
- [ ] On 480px viewport, tab-nav sits directly below header when scrolled
- [ ] Desktop layout (>768px) is unchanged

## Work Log

| Date | Action | Learnings |
|------|--------|-----------|
| 2026-02-28 | Created from PR #2 code review | 3/7 review agents flagged this independently |

## Resources

- PR: https://github.com/CnxLuc/iran-crisis-monitor/pull/2
- Line 270: `.tab-nav` sticky positioning
- Line 167: `.site-header` base height
