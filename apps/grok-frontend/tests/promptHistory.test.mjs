import test from 'node:test';
import assert from 'node:assert/strict';
import { rememberPrompt, safePromptHeight } from '../src/lib/promptHistory.ts';

test('prompt snapshots deduplicate and keep latest within 40 entries', () => {
  let history = [];
  for (let i = 0; i < 45; i += 1) {
    history = rememberPrompt(history, `prompt-${i}`, 'flash25', i + 1);
  }
  assert.equal(history.length, 40);
  assert.equal(history[0].prompt, 'prompt-44');
  history = rememberPrompt(history, '  prompt-10  ', 'flash25', 99);
  assert.equal(history.length, 40);
  assert.equal(history[0].prompt, 'prompt-10');
  assert.equal(history.filter(x => x.prompt === 'prompt-10').length, 1);
  assert.equal(rememberPrompt(history, '   ', 'flash25', 101).length, 40);
});

test('saved textarea height survives reload and remains bounded', () => {
  assert.equal(safePromptHeight(null), 180);
  assert.equal(safePromptHeight(330.4), 330);
  assert.equal(safePromptHeight(50), 120);
  assert.equal(safePromptHeight(2000), 900);
});
