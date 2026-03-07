import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const repoRoot = process.cwd();
const htmlPath = path.join(repoRoot, 'public', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');

function extractFunctionSource(functionName) {
  const startToken = `function ${functionName}(`;
  const start = html.indexOf(startToken);
  assert.notEqual(start, -1, `${functionName} must exist in public/index.html`);

  let braceIndex = html.indexOf('{', start);
  assert.notEqual(braceIndex, -1, `${functionName} must include function body`);

  let depth = 0;
  for (let i = braceIndex; i < html.length; i += 1) {
    const ch = html[i];
    if (ch === '{') depth += 1;
    if (ch === '}') depth -= 1;
    if (depth === 0) {
      return html.slice(start, i + 1);
    }
  }

  throw new Error(`Could not parse ${functionName} source`);
}

test('market snapshot hooks exist for ops and economic cards', () => {
  const requiredHooks = [
    'data-indicator="wti" data-field="value"',
    'data-indicator="gold" data-field="value"',
    'data-indicator="btc" data-field="value"',
    'data-indicator="brent" data-field="value"',
    'data-indicator="lmt" data-field="value"',
    'data-indicator="vix" data-field="value"',
    'data-indicator="us10y" data-field="value"',
    'data-indicator="sp500" data-field="value"',
    'data-indicator="wti" data-field="change"',
    'data-indicator="sp500" data-field="change"',
  ];
  requiredHooks.forEach((hook) => assert.equal(html.includes(hook), true, `Missing hook: ${hook}`));
});

test('economic impact narrative hooks exist for live copy', () => {
  const requiredIds = [
    'id="economicIndicatorsAsOf"',
    'id="economicBriefWti"',
    'id="economicWatchWti"',
    'id="economicTradeWti"',
    'id="economicTradeWtiChange"',
    'id="economicTradeGold"',
    'id="economicTradeLmt"',
    'id="economicTradeLmtChange"',
    'id="economicTradeVix"',
  ];
  requiredIds.forEach((hook) => assert.equal(html.includes(hook), true, `Missing economic hook: ${hook}`));
});

test('renderMarketSnapshot updates value and change fields with direction classes', () => {
  const fnSource = extractFunctionSource('renderMarketSnapshot');
  const helperSource = extractFunctionSource('applyMarketDirectionClass');
  const nodes = [
    {
      dataset: { indicator: 'wti', field: 'value' },
      textContent: '$0.00',
      classList: { add() {}, remove() {} },
    },
    {
      dataset: { indicator: 'wti', field: 'change' },
      textContent: '',
      classList: {
        classes: new Set(['change-down']),
        add(name) { this.classes.add(name); },
        remove(name) { this.classes.delete(name); },
      },
    },
  ];

  const context = {
    document: {
      querySelectorAll(selector) {
        assert.equal(selector, '[data-indicator][data-field]');
        return nodes;
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(
    `${helperSource}; ${fnSource}; this.renderMarketSnapshot = renderMarketSnapshot;`,
    context
  );
  context.renderMarketSnapshot({
    indicators: {
      wti: {
        valueDisplay: '$67.40',
        changeDisplay: '▲ +8.2%',
        direction: 'up',
      },
    },
  });

  assert.equal(nodes[0].textContent, '$67.40');
  assert.equal(nodes[1].textContent, '▲ +8.2%');
  assert.equal(nodes[1].classList.classes.has('change-up'), true);
  assert.equal(nodes[1].classList.classes.has('change-down'), false);
});

test('renderEconomicImpactSnapshot updates economic copy from snapshot', () => {
  const formatDateSource = extractFunctionSource('formatMarketDate');
  const formatTimestampSource = extractFunctionSource('formatSnapshotTimestamp');
  const classHelperSource = extractFunctionSource('applyMarketDirectionClass');
  const renderSource = extractFunctionSource('renderEconomicImpactSnapshot');
  const ids = {
    economicIndicatorsAsOf: { textContent: '' },
    economicBriefWti: { textContent: '' },
    economicWatchWti: { textContent: '' },
    economicTradeWti: { textContent: '' },
    economicTradeWtiChange: {
      textContent: '',
      classList: {
        classes: new Set(['change-down']),
        add(name) { this.classes.add(name); },
        remove(name) { this.classes.delete(name); },
      },
    },
    economicTradeGold: { textContent: '' },
    economicTradeLmt: { textContent: '' },
    economicTradeLmtChange: {
      textContent: '',
      classList: {
        classes: new Set(),
        add(name) { this.classes.add(name); },
        remove(name) { this.classes.delete(name); },
      },
    },
    economicTradeVix: { textContent: '' },
  };

  const context = {
    document: {
      getElementById(id) {
        return ids[id] || null;
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(
    `${formatDateSource}; ${formatTimestampSource}; ${classHelperSource}; ${renderSource}; this.renderEconomicImpactSnapshot = renderEconomicImpactSnapshot;`,
    context
  );

  context.renderEconomicImpactSnapshot({
    asOf: '2026-03-07T12:34:00Z',
    indicators: {
      wti: { valueDisplay: '$81.25', changeDisplay: '▲ +3.4%', direction: 'up' },
      gold: { valueDisplay: '$3,025' },
      lmt: { valueDisplay: '$512.30', changeDisplay: '▼ -1.1%', direction: 'down' },
      vix: { valueDisplay: '31.7' },
    },
  });

  assert.equal(ids.economicIndicatorsAsOf.textContent, '(Mar 7, 2026 12:34 GMT)');
  assert.equal(ids.economicBriefWti.textContent, '$81.25 WTI');
  assert.equal(ids.economicWatchWti.textContent, '$81.25');
  assert.equal(ids.economicTradeWti.textContent, '$81.25 WTI');
  assert.equal(ids.economicTradeWtiChange.textContent, '▲ +3.4%');
  assert.equal(ids.economicTradeWtiChange.classList.classes.has('change-up'), true);
  assert.equal(ids.economicTradeWtiChange.classList.classes.has('change-down'), false);
  assert.equal(ids.economicTradeGold.textContent, '$3,025');
  assert.equal(ids.economicTradeLmt.textContent, '$512.30');
  assert.equal(ids.economicTradeLmtChange.textContent, '▼ -1.1%');
  assert.equal(ids.economicTradeLmtChange.classList.classes.has('change-down'), true);
  assert.equal(ids.economicTradeVix.textContent, '31.7');
});

test('fallback data includes market snapshot for economic section hydration', () => {
  const snapshotSource = extractFunctionSource('getFallbackMarketSnapshot');
  const dataSource = extractFunctionSource('getFallbackData');
  const context = { Math, Date };

  vm.createContext(context);
  vm.runInContext(
    `${snapshotSource}; ${dataSource}; this.getFallbackData = getFallbackData;`,
    context
  );

  const fallback = context.getFallbackData();
  assert.equal(fallback.marketSnapshot.indicators.wti.valueDisplay, '$67.40');
  assert.equal(fallback.marketSnapshot.indicators.vix.changeDisplay, '▲ +9.3 pts');
});

test('applyData invokes market and economic snapshot renderers', () => {
  const hasInvoke = /renderMarketSnapshot\(data\.marketSnapshot\)/.test(html);
  const hasEconomicInvoke = /renderEconomicImpactSnapshot\(data\.marketSnapshot\)/.test(html);
  assert.equal(hasInvoke, true, 'applyData should call renderMarketSnapshot(data.marketSnapshot)');
  assert.equal(hasEconomicInvoke, true, 'applyData should call renderEconomicImpactSnapshot(data.marketSnapshot)');
});
