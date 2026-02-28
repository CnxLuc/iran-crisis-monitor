---
status: pending
priority: p3
issue_id: "003"
tags: [code-review, security, xss, pre-existing]
dependencies: []
---

# Pre-existing XSS: Unsanitized API data injected via innerHTML

## Problem Statement

Several render functions inject API response data directly into `innerHTML` via template literals without escaping. If the API returns malicious content (e.g., `<img onerror=alert(1)>` in a title), it would execute as XSS. **This is NOT introduced by PR #2** but was discovered during the review.

## Findings

- **Source**: Security Sentinel
- **Location**:
  - `renderNews()` ~line 3575-3596: `item.source`, `item.title`, `item.excerpt`, `item.url` injected raw
  - `renderMarkets()` ~line 3608-3619: `m.url`, `m.question` injected raw
  - `renderPmTrends()` ~line 3688: `m.question` injected raw
  - `renderChatMessage()` ~line 4124: `msg.color` injected into style attribute (partial escape bypass)
- **Note**: The codebase has an `escHtml()` function (line 4216-4219) that works correctly but is not used in all render paths
- **Risk level**: Medium — depends on API trust level and CSP headers

## Proposed Solutions

### Option A: Use escHtml() consistently
Apply the existing `escHtml()` function to all user-facing API data before innerHTML injection. Validate `msg.color` against a regex like `/^#[0-9a-f]{3,6}$/i`.
- **Effort**: Small-Medium
- **Risk**: Low

### Option B: Switch to DOM API
Use `createElement` + `textContent` instead of innerHTML template literals.
- **Effort**: Medium-Large
- **Risk**: Low

## Technical Details

- **Affected files**: `public/index.html`
- **Components**: `renderNews()`, `renderMarkets()`, `renderPmTrends()`, `renderChatMessage()`

## Acceptance Criteria

- [ ] All API data is escaped before innerHTML injection
- [ ] `msg.color` is validated against an allowlist or regex
- [ ] Existing `escHtml()` function is used in all render paths

## Work Log

| Date | Action | Learnings |
|------|--------|-----------|
| 2026-02-28 | Created from PR #2 code review | Pre-existing issue, not introduced by this PR |

## Resources

- PR: https://github.com/CnxLuc/iran-crisis-monitor/pull/2
