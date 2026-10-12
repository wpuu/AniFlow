import test from 'node:test';
import assert from 'node:assert/strict';
import { buildSafeTrialReport } from '../src/lib/safeTrialReport.ts';

test('sanitized report includes counts and outcomes but never leaks secrets or signed URLs', () => {
  const key = 'VERY_SENSITIVE_AGNES_KEY_DO_NOT_COPY';
  const url = 'https://cdn.example/video.mp4?signature=VERY_SENSITIVE_SIGNATURE';
  const id = 'VERY_SENSITIVE_VIDEO_ID';
  const prompt = 'SECRET_PROMPT_DO_NOT_INCLUDE';
  const rawError = 'queue_full account secret ' + key;
  const result = buildSafeTrialReport(
    [true, true, false],
    [
      {id: 'secret-task-id', keyIndex: 0, createdAt: 1000, finishedAt: 61000,
        promptPreview: prompt, modelKey: 'flash25', mode: 't2v', ratio:'9:16',
        resolution:'720p', status:'completed', progress:100,
        videoUrl:url, videoId:id, taskId:'VERY_SENSITIVE_TASK_ID', error:null},
      {id: 'task-2', keyIndex: 1, createdAt: 2000, promptPreview: prompt,
        modelKey: 'flash25', mode: 't2v', ratio:'9:16', resolution:'720p',
        status:'failed', progress:0, videoUrl:null, videoId:null,
        taskId:null, error:rawError},
    ],
    [1],
    121000,
  );
  for (const secret of [key,url,id,prompt,'VERY_SENSITIVE_TASK_ID','signature','secret-task-id',rawError]) {
    assert.equal(result.includes(secret),false, secret);
  }
  const obj=JSON.parse(result);
  assert.equal(obj.configured_count,2);
  assert.equal(obj.keys[0].elapsed_to_final_seconds,60);
  assert.equal(obj.keys[0].has_download_url,true);
  assert.equal(obj.keys[1].error_category,'queue_full');
  assert.equal(obj.keys[1].has_unresolved_submission,true);
  assert.equal(obj.keys[2].status,'none');
});

test('malformed browser histories never export arbitrary status or negative timestamps', () => {
  const result = JSON.parse(buildSafeTrialReport([true],
    [{id:'x',keyIndex:0,createdAt:100000,finishedAt:1,
      promptPreview:'SECRET_PROMPT',mode:'unknown',ratio:'unknown',
      resolution:'unknown',status:'SECRET_STATUS',modelKey:'SECRET_MODEL',
      progress:30,videoUrl:null,videoId:null,taskId:null,error:'SECRET_ERROR'}],
    [],110000));
  assert.equal(result.keys[0].status,'unknown');
  assert.equal(result.keys[0].model,'unknown');
  assert.equal(result.keys[0].elapsed_to_final_seconds,null);
  assert.equal(result.keys[0].error_category,'other');
  assert.equal(JSON.stringify(result).includes('SECRET_'),false);
});
