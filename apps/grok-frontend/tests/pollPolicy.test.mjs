import test from 'node:test';
import assert from 'node:assert/strict';
import {
  STATUS_POLL_WINDOW_MS,
  isWithinStatusWindow,
  retryableStatusDelayMs,
} from '../src/lib/pollPolicy.ts';

test('retry only read-only recoverable status failures', () => {
  assert.equal(retryableStatusDelayMs('HTTP 404: task not found'), 12000);
  assert.equal(retryableStatusDelayMs('HTTP 429: slow down'), 30000);
  assert.equal(retryableStatusDelayMs('HTTP 503: upstream unavailable'), 25000);
  assert.equal(retryableStatusDelayMs('HTTP 504: timeout'), 25000);
  assert.equal(retryableStatusDelayMs('Failed to fetch'), 15000);
  for (const code of [400, 401, 403, 409, 422]) {
    assert.equal(retryableStatusDelayMs('HTTP ' + code + ': rejected'), null);
  }
  assert.equal(retryableStatusDelayMs('invalid JSON'), null);
});

test('finite and monotonic 20-minute tracking window', () => {
  assert.equal(isWithinStatusWindow(1000, 1000), true);
  assert.equal(isWithinStatusWindow(1000, 1000 + STATUS_POLL_WINDOW_MS - 1), true);
  assert.equal(isWithinStatusWindow(1000, 1000 + STATUS_POLL_WINDOW_MS), false);
  assert.equal(isWithinStatusWindow(1000, 999), false);
  assert.equal(isWithinStatusWindow(Number.NaN, Date.now()), false);
});
