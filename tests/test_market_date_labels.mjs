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

test('formatMarketDate normalizes ISO date to "Mon D, YYYY"', () => {
  const formatSource = extractFunctionSource('formatMarketDate');
  const context = {};
  vm.createContext(context);
  vm.runInContext(`${formatSource}; this.formatMarketDate = formatMarketDate;`, context);

  assert.equal(context.formatMarketDate('2026-03-31T23:59:59Z'), 'Mar 31, 2026');
  assert.equal(context.formatMarketDate(''), '');
});

test('marketResolutionSuffix creates a resolves label when a date is available', () => {
  const formatSource = extractFunctionSource('formatMarketDate');
  const suffixSource = extractFunctionSource('marketResolutionSuffix');
  const context = {};
  vm.createContext(context);
  vm.runInContext(
    `${formatSource}; ${suffixSource}; this.marketResolutionSuffix = marketResolutionSuffix;`,
    context
  );

  assert.equal(
    context.marketResolutionSuffix({ question: 'Will X happen?', endDate: '2026-03-31T23:59:59Z' }),
    ' · Resolves Mar 31, 2026'
  );
  assert.equal(context.marketResolutionSuffix({ question: 'Will X happen?' }), '');
});

test('marketDisplayQuestion expands ellipsis titles with non-binary top outcome labels', () => {
  const displaySource = extractFunctionSource('marketDisplayQuestion');
  const context = {};
  vm.createContext(context);
  vm.runInContext(`${displaySource}; this.marketDisplayQuestion = marketDisplayQuestion;`, context);

  assert.equal(
    context.marketDisplayQuestion({
      question: 'US next strikes Iran on...?',
      outcomes: [{ label: 'Mar 1, 2026' }]
    }),
    'US next strikes Iran on Mar 1, 2026?'
  );

  assert.equal(
    context.marketDisplayQuestion({
      question: 'Will Iran close Hormuz?',
      outcomes: [{ label: 'Yes' }]
    }),
    'Will Iran close Hormuz?'
  );
});

test('cards use display question helper and resolve date metadata suffix', () => {
  assert.equal(
    html.includes('${marketDisplayQuestion(m)}'),
    true,
    'market cards should render marketDisplayQuestion(m)'
  );

  const sidebarHasResolveLabel = /\$\{m\.volumeFormatted \|\| ''\} vol · Polymarket\$\{marketResolutionSuffix\(m\)\}/.test(html);
  const trendHasResolveLabel = /\$\{m\.volumeFormatted \|\| '\\u2014'\} vol \\u00b7 Polymarket\$\{marketResolutionSuffix\(m\)\}/.test(html);
  assert.equal(sidebarHasResolveLabel, true, 'sidebar metadata should include resolve label suffix');
  assert.equal(trendHasResolveLabel, true, 'trend metadata should include resolve label suffix');
});
