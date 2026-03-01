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

test('renderMarketSnapshot updates value and change fields with direction classes', () => {
  const fnSource = extractFunctionSource('renderMarketSnapshot');
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
  vm.runInContext(`${fnSource}; this.renderMarketSnapshot = renderMarketSnapshot;`, context);
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

test('applyData invokes market snapshot renderer', () => {
  const hasInvoke = /renderMarketSnapshot\(data\.marketSnapshot\)/.test(html);
  assert.equal(hasInvoke, true, 'applyData should call renderMarketSnapshot(data.marketSnapshot)');
});
