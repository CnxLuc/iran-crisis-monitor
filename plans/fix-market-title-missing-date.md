# fix: Show resolution date in prediction market cards

## Problem

When a Polymarket market title is generic (e.g. "Iran nuclear deal"), the sidebar card shows something like **"0.1% — Iran nuclear deal"** with no indication of *when* the market resolves. The user sees a probability but has no context for the timeframe, making the data misleading.

**Root cause:** The `question` field from the Polymarket API sometimes contains a date ("Will X happen by March 2026?") and sometimes doesn't. The frontend renders `m.question` verbatim with no date extraction or fallback.

## Proposed Solution

Extract and display the market's **end date** (resolution date) on each market card. Two places render markets:

1. **Sidebar cards** (`renderMarkets()` — `index.html:3575`)
2. **Trend cards** (`renderPmTrends()` — `index.html:3638`)

### Backend: Pass `endDate` from the API

In `api/live.py:235-291`, each Polymarket event has an `endDate` field in the Gamma API response. Extract it and include it in the market object.

```python
# api/live.py — inside fetch_polymarket(), around line 282
markets.append({
    "question": title,
    "endDate": event.get("endDate", ""),   # <-- ADD THIS
    "volume": total_volume,
    ...
})
```

### Frontend: Display the resolution date

In both `renderMarkets()` and `renderPmTrends()`, add a small date label next to the volume line when `m.endDate` exists.

**Sidebar card** (`index.html:3586-3592`):
```html
<div class="market-compact-vol">
  ${m.volumeFormatted || ''} vol · Polymarket
  ${m.endDate ? ' · Resolves ' + formatMarketDate(m.endDate) : ''}
</div>
```

**Trend card** (`index.html:3690`):
```html
<span class="pm-trend-vol">
  ${m.volumeFormatted || '—'} vol · Polymarket
  ${m.endDate ? ' · Resolves ' + formatMarketDate(m.endDate) : ''}
  ${horizonLabel ? ' · ' + horizonLabel : ''}
</span>
```

**Date formatter** (add near the render functions):
```javascript
function formatMarketDate(iso) {
  try {
    const d = new Date(iso);
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return months[d.getUTCMonth()] + ' ' + d.getUTCDate() + ', ' + d.getUTCFullYear();
  } catch(e) { return ''; }
}
```

### Fallback data: Add `endDate` to hardcoded markets

Update `getFallbackData()` (`index.html:3861-3868`) to include `endDate` for each fallback market so the date shows even when the API is down.

## Acceptance Criteria

- [ ] Each market card shows its resolution date (e.g. "Resolves Mar 31, 2026")
- [ ] Date appears in both sidebar and trend card views
- [ ] When `endDate` is missing from the API, no date label is shown (graceful fallback)
- [ ] Fallback data includes `endDate` values

## Files to Change

| File | Lines | Change |
|------|-------|--------|
| `api/live.py` | ~282 | Add `endDate` to market dict |
| `public/index.html` | ~3575-3595 | Update `renderMarkets()` template |
| `public/index.html` | ~3684-3696 | Update `renderPmTrends()` template |
| `public/index.html` | ~3572 | Add `formatMarketDate()` helper |
| `public/index.html` | ~3861-3868 | Add `endDate` to fallback data |
