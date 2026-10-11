import test from 'node:test';
import assert from 'node:assert/strict';
import {
  attachVideoId,
  isValidSubmissionGuards,
  releaseAttempt,
  reserveAttempt,
} from '../src/lib/taskSafety.ts';

const a = { attemptId: 'local-attempt-1', keyIndex: 0, modelKey: 'flash25', createdAt: 1, videoId: null };
const b = { attemptId: 'local-attempt-2', keyIndex: 0, modelKey: 'flash25', createdAt: 2, videoId: null };

test('initial ledger is valid; malformed ledger is rejected fail-closed', () => {
  assert.equal(isValidSubmissionGuards({}), true);
  assert.equal(isValidSubmissionGuards({ '0': a }), true);
  assert.equal(isValidSubmissionGuards([]), false);
  assert.equal(isValidSubmissionGuards({ '0': { ...a, attemptId: '' } }), false);
  assert.equal(isValidSubmissionGuards({ '0': { ...a, modelKey: 'wan' } }), false);
  assert.equal(isValidSubmissionGuards({ '9': { ...a, keyIndex: 9 } }), false);
  assert.equal(isValidSubmissionGuards({ '0': { ...a, videoId: undefined } }), false);
});

test('one unresolved attempt per key blocks a second POST', () => {
  const first = reserveAttempt({}, a);
  assert.deepEqual(first, { '0': a });
  assert.equal(reserveAttempt(first, b), null);
  assert.equal(first['0'].attemptId, 'local-attempt-1');
});

test('different key positions may reserve independently', () => {
  const first = reserveAttempt({}, a);
  const second = reserveAttempt(first, { ...b, keyIndex: 1 });
  assert.equal(isValidSubmissionGuards(second), true);
  assert.equal(Object.keys(second).length, 2);
});

test('only matching attempt can attach video_id or release guard', () => {
  const first = reserveAttempt({}, a);
  assert.equal(attachVideoId(first, 0, 'another-attempt', 'video_x'), first);
  assert.equal(attachVideoId(first, 0, a.attemptId, ''), first);
  const withId = attachVideoId(first, 0, a.attemptId, 'video_real_1');
  assert.equal(withId['0'].videoId, 'video_real_1');
  assert.equal(first['0'].videoId, null);
  assert.equal(releaseAttempt(withId, 0, 'another-attempt'), withId);
  assert.deepEqual(releaseAttempt(withId, 0, a.attemptId), {});
});

test('serialization preserves unresolved ledger through a page reload', () => {
  const persisted = JSON.stringify(attachVideoId(reserveAttempt({}, a), 0, a.attemptId, 'video_123'));
  const restored = JSON.parse(persisted);
  assert.equal(isValidSubmissionGuards(restored), true);
  assert.equal(reserveAttempt(restored, b), null);
});
