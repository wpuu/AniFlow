// Local response-contract tests only. These never contact AWS or generate video.
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

test("Wan health requires its exact identity pair and current readiness", () => {
  const health = {mode:"REAL_WAN", provider:"wan2.2-i2v-a14b", simulation:false,
    ready:true, tunnel_connected:true, gpu_connected:true, blocked_reasons:[]};
  assert.equal(realServiceHealth(health, "real").provider, "wan2.2-i2v-a14b");
  assert.equal(realServiceHealth({...health, ready:false}, "real").ready, false);
  assert.equal(realServiceHealth({...health, gpu_connected:false}, "real").ready, false);
  assert.equal(realServiceHealth({...health, tunnel_connected:false}, "real").ready, false);
  assert.equal(realServiceHealth(health, "mock").ready, false);
  for (const broken of [{...health, mode:"REAL_H3"}, {...health, provider:"minimax-h3"},
    {...health, provider:"some-other-model"}, {...health, simulation:true}]) {
    assert.throws(()=>realServiceHealth(broken, "real"), /真实服务身份/);
  }
});

test("Wan history keeps its own model and never invents completion or metrics", () => {
  const wan = {...realJob, id:"wan-test", provider:"wan2.2-i2v-a14b"};
  for (const status of ["running", "submission_unknown", "downloading"]) {
    const task = toTask({...wan, status, video_download_path:"/api/studio/real/jobs/wan-test/video"}, "real");
    assert.equal(task.modelId, "wan2.2-i2v-a14b");
    assert.equal(task.videoUrl, undefined);
    assert.equal(task.cost, null);
    assert.equal(task.etaSeconds, null);
  }
  assert.equal(toTask(realJob, "real").modelId, "minimax-h3");
  assert.throws(()=>toTask(wan, "mock"), /任务来源/);
  assert.throws(()=>toTask({...wan, provider:"unknown-model"}, "real"), /任务来源/);
  const completed = {...wan, status:"completed", verified:true, local_path:"G:/outputs/Wan.mp4",
    output_sha256:"c".repeat(64), output_bytes:4096,
    video_metadata:{width:774, height:1376, duration_seconds:5, fps:24, frame_count:120, sample_aspect_ratio:"1:1"},
    video_download_path:"/api/studio/real/jobs/wan-test/video"};
  assert.equal(toTask(completed, "real").status, "done");
  assert.throws(()=>toTask({...completed, verified:false}, "real"), /不能显示完成/);
  for (const metadata of [{...completed.video_metadata, width:720},
    {...completed.video_metadata, duration_seconds:121/24}, {...completed.video_metadata, fps:16},
    {...completed.video_metadata, frame_count:121}, {...completed.video_metadata, sample_aspect_ratio:"2:1"}]) {
    assert.throws(()=>toTask({...completed, video_metadata:metadata}, "real"), /不能显示完成/);
  }
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
  assert.throws(()=>parseCloudPreflight({...projection, service:"ec2"}, "real"), /本机审计投影/);
  assert.throws(()=>parseCloudPreflight({...projection, mode:"UNVERIFIED_PLACEHOLDER"}, "real"), /本机审计投影/);
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

test("GameLift preflight requires its private S3, CUDA and both release safeguards", () => {
  const keys = ["credit_gamelift_eligible", "credit_expiry_confirmed", "tokyo_gamelift_quota",
    "tokyo_capacity_and_price", "private_s3_connectivity", "h3_license_territory",
    "gpu_stop_safeguard", "independent_stop_safeguard", "account_plan_unchanged", "runtime_cuda_verified"];
  const projection = {mode:"LOCAL_AUDIT_PROJECTION", service:"gameliftstreams",
    checks:Object.fromEntries(keys.map(key=>[key,null])), launch_allowed:false, real_gpu_connected:false};
  assert.equal(parseCloudPreflight(projection,"real").checks.runtime_cuda_verified,null);
  for (const required of ["private_s3_connectivity", "independent_stop_safeguard", "runtime_cuda_verified"]) {
    const broken = {...projection, checks:{...projection.checks}};
    delete broken.checks[required];
    assert.throws(()=>parseCloudPreflight(broken,"real"), /必要安全字段/);
  }
});

test("Wan EC2 projection is bound to its model, Ohio, exact instance and hardware", () => {
  const keys = ["credit_ec2_eligible", "credit_expiry_confirmed", "ohio_gpu_quota",
    "ohio_capacity_and_price", "ssm_private_connectivity", "wan_license_verified",
    "gpu_stop_safeguard", "independent_stop_safeguard", "account_plan_unchanged", "native_video_spec_confirmed"];
  const projection = {mode:"LOCAL_AUDIT_PROJECTION", provider:"wan2.2-i2v-a14b", service:"ec2",
    region:"us-east-2", instance_type:"g7e.2xlarge", expected_ram_gib:64, expected_gpu_vram_gib:96,
    checks:Object.fromEntries(keys.map(key=>[key,null])), launch_allowed:false, real_gpu_connected:false};
  assert.equal(parseCloudPreflight(projection, "real").provider, "wan2.2-i2v-a14b");
  assert.equal(parseCloudPreflight(projection, "real").launch_allowed, false);
  for (const broken of [{...projection, provider:"minimax-h3"}, {...projection, region:"ap-northeast-1"},
    {...projection, instance_type:"g6.2xlarge"}, {...projection, service:"workspaces"}]) {
    assert.throws(()=>parseCloudPreflight(broken, "real"), /本机审计投影/);
  }
  for (const required of keys) {
    const broken = {...projection, checks:{...projection.checks}};
    delete broken.checks[required];
    assert.throws(()=>parseCloudPreflight(broken, "real"), /必要安全字段/);
  }
  assert.throws(()=>parseCloudPreflight({...projection, expected_gpu_vram_gib:24}, "real"), /必要安全字段/);
  assert.throws(()=>parseCloudPreflight({...projection, expected_ram_gib:"64"}, "real"), /必要安全字段/);
  assert.throws(()=>parseCloudPreflight({...projection, launch_allowed:true}, "real"), /必要安全字段/);
  const ready = {...projection, checks:Object.fromEntries(keys.map(key=>[key,true])),
    launch_allowed:true, real_gpu_connected:true, tunnel_connected:true};
  assert.equal(parseCloudPreflight(ready, "real").launch_allowed, true);
  assert.throws(()=>parseCloudPreflight({...ready, tunnel_connected:false}, "real"), /必要安全字段/);
});

test("Wan preflight accepts exact deployed L4 hardware without confusing RAM and VRAM", () => {
  const keys = ["credit_ec2_eligible", "credit_expiry_confirmed", "ohio_gpu_quota",
    "ohio_capacity_and_price", "ssm_private_connectivity", "wan_license_verified",
    "gpu_stop_safeguard", "independent_stop_safeguard", "account_plan_unchanged", "native_video_spec_confirmed"];
  const base = {mode:"LOCAL_AUDIT_PROJECTION", provider:"wan2.2-i2v-a14b", service:"ec2",
    region:"us-east-2", checks:Object.fromEntries(keys.map(key=>[key,null])),
    launch_allowed:false, real_gpu_connected:false};
  for (const hardware of [
    {instance_type:"g6.xlarge", expected_gpu:"NVIDIA L4", expected_ram_gib:16, expected_gpu_vram_gib:22888/1024},
    {instance_type:"g6e.2xlarge", expected_gpu:"NVIDIA L40S", expected_ram_gib:64, expected_gpu_vram_gib:45776/1024},
    {instance_type:"g7e.2xlarge", expected_gpu:"NVIDIA RTX PRO Server 6000", expected_ram_gib:64, expected_gpu_vram_gib:96},
  ]) {
    assert.equal(parseCloudPreflight({...base, ...hardware}, "real").instance_type, hardware.instance_type);
    assert.throws(()=>parseCloudPreflight({...base, ...hardware, expected_ram_gib:128}, "real"), /目标硬件不符/);
    assert.throws(()=>parseCloudPreflight({...base, ...hardware, expected_gpu_vram_gib:16}, "real"), /目标硬件不符/);
    assert.throws(()=>parseCloudPreflight({...base, ...hardware, expected_gpu:"Pretend GPU"}, "real"), /目标硬件不符/);
  }
  const label = preflightModule.exports.formatExpectedHardware({...base, instance_type:"g6.xlarge",
    expected_gpu:"NVIDIA L4", expected_ram_gib:16, expected_gpu_vram_gib:22888/1024});
  assert.match(label, /目标硬件（未实测）/);
  assert.match(label, /g6\.xlarge \/ NVIDIA L4 \/ 22\.35GiB 显存 \/ 16GiB 内存/);
});

test("fresh validated Wan service identity supplies the submitted provider", async () => {
  const calls = [];
  const local = new Map();
  const accepted = {...realJob, provider:"wan2.2-i2v-a14b"};
  const react = {useCallback:fn=>fn, useEffect:()=>{}, useMemo:fn=>fn(), useRef:value=>({current:value}),
    useState:value=>[typeof value === "function" ? value() : value, ()=>{}]};
  const context = {exports:{}, require:()=>react, Date, Error, console, Blob, FormData,
    localStorage:{getItem:key=>local.get(key) ?? null, setItem:(key,value)=>local.set(key,value), removeItem:key=>local.delete(key)},
    crypto:{randomUUID:()=>"wan-create-contract-key"},
    fetch:async (url, options) => {
      calls.push({url, options});
      if (url === "/api/studio/real/health") return {ok:true, status:200, json:async()=>({
        mode:"REAL_WAN", provider:"wan2.2-i2v-a14b", simulation:false, ready:true,
        tunnel_connected:true, gpu_connected:true, blocked_reasons:[]})};
      if (url.startsWith("data:image/")) return {blob:async()=>new Blob(["image"],{type:"image/png"})};
      if (url.endsWith("/assets")) return {ok:true, json:async()=>({image_id:"a".repeat(64)})};
      if (url.endsWith("/jobs")) return {ok:true, json:async()=>accepted};
      throw new Error("Unexpected local contract request");
    }};
  vm.runInNewContext(compiled, context);
  const engine = context.exports.useTaskEngine("real");
  const payload = {firstFrame:"data:image/png;base64,aW1hZ2U=",
    prompt:"Owner motion", negativePrompt:"", modelId:"wan2.2-i2v-a14b", duration:5, aspectRatio:"9:16"};
  const task = await engine.createTask(payload);
  assert.equal(task.modelId, "wan2.2-i2v-a14b");
  assert.equal(JSON.parse(calls.find(call=>call.url.endsWith("/jobs")).options.body).provider, "wan2.2-i2v-a14b");
  assert.equal(calls.filter(call=>call.url.endsWith("/jobs")).length, 1);
  await assert.rejects(()=>engine.createTask({...payload, modelId:"minimax-h3"}), /真实模型已变更/);
  assert.equal(calls.filter(call=>call.url.endsWith("/jobs")).length, 1);
});

function renderComponent(relativePath, exportName, props) {
  const modules = new Map();
  function load(file) {
    if (modules.has(file)) return modules.get(file);
    const context = {exports:{}, require:id=>{
      if (!id.startsWith(".")) return require(id);
      const base = path.resolve(path.dirname(file), id);
      const target = [base + ".ts", base + ".tsx"].find(candidate=>fs.existsSync(candidate));
      if (!target) throw new Error("Unexpected local UI dependency");
      return load(target);
    }};
    modules.set(file, context.exports);
    vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, "utf8"), {
      compilerOptions:{module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2020, jsx:ts.JsxEmit.ReactJSX},
    }).outputText, context);
    return context.exports;
  }
  const component = load(path.join(__dirname, relativePath))[exportName];
  return require("react-dom/server").renderToStaticMarkup(require("react").createElement(component, props));
}

test("Wan player exposes real file evidence and hides unsupported sampling metrics", () => {
  const task = toTask({...realJob, provider:"wan2.2-i2v-a14b"}, "real");
  const html = renderComponent("../src/components/PlayerModal.tsx", "PlayerModal", {
    task, onClose:()=>{}, onDownload:()=>{},
  });
  assert.match(html, /Wan2\.2 I2V A14B/);
  assert.match(html, /真实生成与本机文件证据/);
  assert.match(html, /尚未保存/);
  assert.match(html, /尚未校验/);
  assert.doesNotMatch(html, />Seed<|>CFG<|>运动<|MiniMax H3/);
});

test("Wan preflight displays Ohio and unverified target specifications", () => {
  const html = renderComponent("../src/components/AwsPreflightPanel.tsx", "AwsPreflightPanel", {
    mode:"real", realProvider:"wan2.2-i2v-a14b", onClose:()=>{},
  });
  assert.match(html, /俄亥俄州 Wan2\.2/);
  assert.match(html, /us-east-2/);
  assert.match(html, /尚未核验/);
  assert.doesNotMatch(html, /g7e\.2xlarge|96GiB|64GiB/);
  assert.match(html, /原生视频规格核验/);
  assert.match(html, /目标硬件（未实测）/);
  assert.doesNotMatch(html, /H3 使用地域与许可/);
});

test("real model card follows health readiness for Wan and H3 while Mock stays unchanged", () => {
  for (const provider of ["wan2.2-i2v-a14b", "minimax-h3"]) {
    for (const ready of [false, true]) {
      const html = renderComponent("../src/components/CreatePanel.tsx", "CreatePanel", {
        mode:"real", realProvider:provider, ready, disabled:!ready, busyCount:0, onSubmit:()=>{},
      });
      assert.match(html, ready ? /就绪/ : /离线/);
      assert.doesNotMatch(html, ready ? /离线/ : /就绪/);
      assert.match(html, /目标硬件：等待本机预检核验/);
      assert.match(html, /生成显存峰值待测/);
      assert.doesNotMatch(html, /720[Pp]|高级参数/);
    }
  }
  const mock = renderComponent("../src/components/CreatePanel.tsx", "CreatePanel", {
    mode:"mock", realProvider:null, ready:false, busyCount:0, onSubmit:()=>{},
  });
  assert.match(mock, /H3 模拟节点/);
  assert.match(mock, /就绪/);
  assert.doesNotMatch(mock, /生成显存峰值待测/);
});
