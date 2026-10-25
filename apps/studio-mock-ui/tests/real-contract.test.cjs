// Local response-contract tests only. These never contact AWS or generate H3 video.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("typescript");

const source = fs.readFileSync(path.join(__dirname, "../src/hooks/useTaskEngine.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const sandbox = {exports:{}, require:()=>({}), Date, Error, console};
vm.runInNewContext(compiled, sandbox);
const {toTask} = sandbox.exports;
const realJob = {
  id:"h3-test", image_id:"a".repeat(64), prompt:"Local contract test",
  negative_prompt:"", aspect_ratio:"9:16", duration_seconds:5,
  provider:"minimax-h3", simulation:false, gpu_connected:true,
  status:"running", progress:null, actual_cost_usd:null, created_at:1,
  video_download_path:null,
};

test("real unknown metrics remain unknown and cannot expose video early", () => {
  const task = toTask({...realJob, video_download_path:"/api/studio/real/jobs/h3-test/video"}, "real");
  assert.equal(task.cost, null);
  assert.equal(task.etaSeconds, null);
  assert.equal(task.progress, null);
  assert.equal(task.videoUrl, undefined);
});

test("completed real jobs require verified local file, hash, bytes and MP4 metadata", () => {
  const completed = {...realJob, status:"completed", verified:true, local_path:"C:/outputs/H3.mp4",
    output_sha256:"b".repeat(64), output_bytes:2048,
    video_metadata:{width:768, height:1360, duration_seconds:5, fps:24},
    video_download_path:"/api/studio/real/jobs/h3-test/video"};
  assert.equal(toTask(completed, "real").status, "done");
  for (const field of ["verified", "local_path", "output_sha256", "output_bytes", "video_metadata"]) {
    const broken = {...completed};
    delete broken[field];
    assert.throws(()=>toTask(broken, "real"), /不能显示完成/);
  }
  assert.throws(()=>toTask({...completed, video_metadata:{...completed.video_metadata, fps:NaN}}, "real"), /不能显示完成/);
});

test("mock and real jobs stay isolated; remote video URLs are refused", () => {
  assert.throws(()=>toTask(realJob, "mock"), /任务来源/);
  assert.throws(()=>toTask({...realJob, simulation:true, provider:"mock-h3"}, "real"), /任务来源/);
  assert.throws(()=>toTask({...realJob, video_download_path:"https://example.com/video.mp4"}, "real"), /视频地址/);
  assert.throws(()=>toTask({...realJob, status:"pretend-success"}, "real"), /未知任务状态/);
});

test("uncertain and downloading states never become completed", () => {
  for (const status of ["submission_unknown", "downloading"]) {
    const task = toTask({...realJob, status}, "real");
    assert.equal(task.status, status);
    assert.equal(task.videoUrl, undefined);
  }
});
