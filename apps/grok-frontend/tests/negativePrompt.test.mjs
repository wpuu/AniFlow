import test from 'node:test';
import assert from 'node:assert/strict';
import { SNOW_DIRECTOR_AVOID, combineVideoPrompt } from '../src/lib/negativePrompt.ts';

test('video 2.5 avoidance is a textual constraint, leaving original editor value intact', () => {
  const original='needle-felted cat blinks beside a water bowl';
  const request=combineVideoPrompt(original,SNOW_DIRECTOR_AVOID);
  assert.ok(request.startsWith(original));
  assert.match(request,/Avoid these unwanted visual elements/);
  assert.match(request,/extra legs or paws/);
  assert.equal(combineVideoPrompt(original,''),original);
  assert.equal(original,'needle-felted cat blinks beside a water bowl');
});
