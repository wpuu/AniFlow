import test from 'node:test';
import assert from 'node:assert/strict';
import { selectGeneratableKeys } from '../src/lib/eligibleKeys.ts';

const state = (status) => ({ status, progress: 0, videoId: null, videoUrl: null, taskId: null, error: null });

test('only configured idle unique keys are selected; active task retains its credential', () => {
  const keys = ['A', 'B', '', 'D', 'E', 'B', 'G', 'H', 'I'];
  const tasks = { 1: state('in_progress'), 3: state('queued'), 6: state('creating') };
  assert.deepEqual(selectGeneratableKeys(keys, 9, tasks), [0, 4, 7, 8]);
});
test('newly submitting slots are protected even before re-render', () => {
  assert.deepEqual(selectGeneratableKeys(['A','B','C','D'], 4, {}, new Set([0,3])), [1,2]);
  assert.deepEqual(selectGeneratableKeys(['A','A','B'], 3, {}), [0,2]);
  assert.deepEqual(selectGeneratableKeys(['',''], 2, {}), []);
});
test('stopped, completed and failed slots remain manually re-creatable', () => {
  const tasks={0:state('stopped'),1:state('completed'),2:state('failed')};
  assert.deepEqual(selectGeneratableKeys(['A','B','C'],3,tasks),[0,1,2]);
});
