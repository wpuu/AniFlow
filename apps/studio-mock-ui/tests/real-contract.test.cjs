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
const {toTask, realServiceHealth} = sandbox.exports;
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

test("tunnel and CUDA evidence are separate and both required for ready", () => {
  const health = {mode:"REAL_H3", provider:"minimax-h3", simulation:false,
    ready:true, tunnel_connected:true, gpu_connected:false, blocked_reasons:[]};
  const cpu = realServiceHealth(health, "real");
  assert.equal(cpu.tunnelConnected, true);
  assert.equal(cpu.gpuConnected, false);
  assert.equal(cpu.ready, false);
  assert.equal(realServiceHealth({...health, gpu_connected:true}, "real").ready, true);
  assert.equal(realServiceHealth({...health, gpu_connected:true, tunnel_connected:false}, "real").ready, false);
  assert.equal(realServiceHealth({...health, gpu_connected:true}, "mock").ready, false);
  const missing = {...health};
  delete missing.tunnel_connected;
  assert.throws(()=>realServiceHealth(missing, "real"), /隧道\/GPU状态/);
});

const preflightSource = fs.readFileSync(path.join(__dirname, "../src/components/AwsPreflightPanel.tsx"), "utf8");
const preflightModule = {exports:{}, require:()=>({}), Error, Number, Object};
vm.runInNewContext(ts.transpileModule(preflightSource, {
  compilerOptions:{module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2020, jsx:ts.JsxEmit.ReactJSX},
}).outputText, preflightModule);
const {parseCloudPreflight} = preflightModule.exports;

test("WorkSpaces preflight accepts only its explicit local audit projection", () => {
  const keys = ["credit_workspaces_eligible", "credit_expiry_confirmed", "tokyo_workspaces_quota",
    "tokyo_capacity_and_price", "ssm_private_connectivity", "h3_license_territory",
    "gpu_stop_safeguard", "independent_stop_safeguard", "account_plan_unchanged", "workspaces_account_eligible"];
  const projection = {mode:"LOCAL_AUDIT_PROJECTION", service:"workspaces",
    checks:Object.fromEntries(keys.map(key=>[key,null])), launch_allowed:false, real_gpu_connected:false,
    estimated_credit_remaining_usd:49.96, credit_settled_remaining_usd:91.14,
    credit_observed_at_utc:"2026-10-25T03:25:00Z"};
  assert.equal(parseCloudPreflight(projection, "real").checks.credit_workspaces_eligible, null);
  assert.equal(parseCloudPreflight(projection, "real").launch_allowed, false);
  assert.throws(()=>parseCloudPreflight({...projection, service:"ec2"}, "real"), /WorkSpaces/);
  assert.throws(()=>parseCloudPreflight({...projection, mode:"UNVERIFIED_PLACEHOLDER"}, "real"), /WorkSpaces/);
  const missing = {...projection, checks:{...projection.checks}};
  delete missing.checks.independent_stop_safeguard;
  assert.throws(()=>parseCloudPreflight(missing, "real"), /必要安全字段/);
  assert.throws(()=>parseCloudPreflight({...projection, estimated_credit_remaining_usd:"49.96"}, "real"), /余额格式/);
});

test("Mock keeps its original seven unknown checks", () => {
  const keys = ["credit_ec2_eligible", "credit_expiry_confirmed", "tokyo_gpu_quota",
    "tokyo_capacity_and_price", "ssm_private_connectivity", "h3_license_territory", "gpu_stop_safeguard"];
  const mock = {mode:"UNVERIFIED_PLACEHOLDER", checks:Object.fromEntries(keys.map(key=>[key,null])),
    launch_allowed:false, real_gpu_connected:false};
  assert.equal(parseCloudPreflight(mock, "mock").mode, "UNVERIFIED_PLACEHOLDER");
});
