import test from 'node:test';
import assert from 'node:assert/strict';
import { percentValue, keyProgressSummary } from '../src/lib/statusProgress.ts';

test('0..100 progress is clamped, complete with playable video is 100, no fake wait', () => {
  assert.equal(percentValue(undefined, 'queued'), 0);
  assert.equal(percentValue(-21, 'in_progress'), 0);
  assert.equal(percentValue(42.4, 'in_progress'), 42);
  assert.equal(percentValue(151, 'in_progress'), 100);
  assert.equal(percentValue(15, 'completed', true), 100);
  assert.equal(percentValue(15, 'completed', false), 15);
});

test('nine Key summaries remain independent and recover from stored history', () => {
  const tasks = { 0: { status: 'in_progress', progress: 57, videoUrl: null, videoId: 'id0' } };
  const history = [
    { keyIndex: 0, createdAt: 100, status: 'queued', progress: 10, videoId: 'id0', videoUrl: null },
    { keyIndex: 1, createdAt: 101, status: 'completed', progress: 100, videoId: 'id1', videoUrl: 'https://cdn.test/test.mp4' },
  ];
  assert.deepEqual(keyProgressSummary(0, tasks, history), { status: 'in_progress', progress: 57 });
  assert.deepEqual(keyProgressSummary(1, tasks, history), { status: 'completed', progress: 100 });
  assert.deepEqual(keyProgressSummary(8, tasks, history), { status: 'idle', progress: 0 });
});
