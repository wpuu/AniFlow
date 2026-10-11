import test from 'node:test';
import assert from 'node:assert/strict';
import {
  attachVideoId,
  duplicateKeySlots,
  isValidSubmissionGuards,
  releaseAttempt,
  reserveAttempt,
  shouldReleaseVideoGuard,
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

test('completed without a usable MP4 address must retain the guard', () => {
  assert.equal(shouldReleaseVideoGuard('completed', null), false);
  assert.equal(shouldReleaseVideoGuard('completed', ''), false);
  assert.equal(shouldReleaseVideoGuard('completed', 'javascript:alert(1)'), false);
  assert.equal(shouldReleaseVideoGuard('queued', 'https://media.test/video.mp4'), false);
  assert.equal(shouldReleaseVideoGuard('completed', 'https://media.test/video.mp4'), true);
  assert.equal(shouldReleaseVideoGuard('failed', null), true);
});

test('duplicate credential slots are detected without returning raw secrets', () => {
  const a = 'TEST_SECRET_A';
  const b = 'TEST_SECRET_B';
  const indexes = duplicateKeySlots([a, '', b, ` ${a} `, b, '']);
  assert.deepEqual(indexes, [3, 4]);
  assert.equal(JSON.stringify(indexes).includes(a), false);
  assert.equal(JSON.stringify(indexes).includes(b), false);
});
