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

test('appendChatQueryParam appends params using correct separator', () => {
  const fnSource = extractFunctionSource('appendChatQueryParam');
  const context = {};
  vm.createContext(context);
  vm.runInContext(`${fnSource}; this.appendChatQueryParam = appendChatQueryParam;`, context);

  const withExistingQuery = context.appendChatQueryParam('/api/chat.py?action=messages', 'since', 'abc');
  assert.equal(withExistingQuery, '/api/chat.py?action=messages&since=abc');

  const withoutQuery = context.appendChatQueryParam('/api/chat/messages', 'since', 'abc');
  assert.equal(withoutQuery, '/api/chat/messages?since=abc');
});

test('pollMessages uses appendChatQueryParam for since cursor', () => {
  const usesHelper = /url\s*=\s*appendChatQueryParam\(url,\s*'since',\s*encodeURIComponent\(chatState\.lastMsgTime\)\)/.test(html);
  assert.equal(usesHelper, true, 'pollMessages should build since query via appendChatQueryParam');
});

test('chat script includes client-side TTL pruning hook', () => {
  const hasPruneFunction = html.includes('function pruneExpiredRenderedMessages(');
  const pollInvokesPrune = /pruneExpiredRenderedMessages\(\)/.test(html);
  assert.equal(hasPruneFunction, true, 'pruneExpiredRenderedMessages should be defined');
  assert.equal(pollInvokesPrune, true, 'chat polling should invoke pruneExpiredRenderedMessages');
});
