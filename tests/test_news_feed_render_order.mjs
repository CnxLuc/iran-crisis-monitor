import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

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

test('renderNews preserves backend ordering and does not resort by time', () => {
  const source = extractFunctionSource('renderNews');
  assert.equal(source.includes('news.map((item, i) =>'), true);
  assert.equal(source.includes('.sort((a, b) => new Date(b.time) - new Date(a.time))'), false);
});
