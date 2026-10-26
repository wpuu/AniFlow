"""Packaged GameLift application: CUDA diagnostics and one durable private H3 job."""
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "agent"))


def run():
    import boto3
    import torch

    from aniflow.studio.comfy_provider import ComfyProvider
    from aniflow.studio.s3_jobs import S3Jobs

    s3 = boto3.client("s3", region_name="ap-northeast-1")
    bucket, prefix = os.environ["ANIFLOW_BUCKET"], "experiments/h3-20261026"
    jobs = S3Jobs(s3, bucket, prefix)
    session = os.environ["ANIFLOW_SESSION_KEY"]
    diagnostics = {"session_key": session, "cuda_verified": False,
                   "torch": torch.__version__, "cuda_runtime": torch.version.cuda,
                   "comfy_kitchen": importlib.metadata.version("comfy-kitchen")}

    def publish(name, value):
        s3.put_object(Bucket=bucket, Key=f"{prefix}/{name}",
            Body=json.dumps(value).encode(), ContentType="application/json",
            ServerSideEncryption="AES256")

    server = None
    try:
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("CUDA is unavailable or GPU count differs from one")
        device = torch.cuda.get_device_properties(0)
        diagnostics.update(device_name=device.name, vram_total_bytes=device.total_memory,
                           capability=list(torch.cuda.get_device_capability(0)))
        if ("L4" not in device.name or device.total_memory < 22000 * 1024**2
                or not str(torch.version.cuda).startswith("13.")):
            raise RuntimeError("Expected full L4 VRAM and CUDA13 runtime")
        torch.cuda.reset_peak_memory_stats()
        tensor = torch.randn((1024, 1024), device="cuda", dtype=torch.bfloat16)
        actual = tensor @ tensor.T
        if not torch.isfinite(actual).all().item():
            raise RuntimeError("CUDA matrix multiply returned non-finite values")
        # Exercise the real pinned INT8 ConvRot implementation, without changing H3 weights.
        from comfy_kitchen.tensor.int8 import TensorWiseINT8Layout
        quantized, params = TensorWiseINT8Layout.quantize(tensor, is_weight=True,
            per_channel=True, convrot=True, convrot_groupsize=256)
        restored = TensorWiseINT8Layout.dequantize(quantized, params)
        if not torch.isfinite(restored).all().item():
            raise RuntimeError("INT8 ConvRot kernel returned non-finite values")
        torch.cuda.synchronize()
        diagnostics["kernel_peak_vram_bytes"] = torch.cuda.max_memory_allocated()
        del tensor, actual, quantized, restored
        torch.cuda.empty_cache()
        with (ROOT / "models.json").open(encoding="utf-8") as source:
            models = json.load(source)
        for asset in models["files"]:
            path = ROOT / "ComfyUI/models" / asset["path"]
            if path.stat().st_size != asset["bytes"]:
                raise RuntimeError("Pinned model size mismatch")
        log = (ROOT / "comfy.log").open("w")
        server = subprocess.Popen([sys.executable, "-B", str(ROOT / "ComfyUI/main.py"),
            "--listen", "127.0.0.1", "--port", "8188", "--disable-auto-launch", "--lowvram"],
            cwd=ROOT / "ComfyUI", stdout=log, stderr=subprocess.STDOUT)
        provider = ComfyProvider("http://127.0.0.1:8188")
        for _ in range(90):
            connected, cuda = provider.connection_state()
            if connected and cuda:
                break
            if server.poll() is not None:
                raise RuntimeError("ComfyUI exited before CUDA readiness")
            time.sleep(2)
        else:
            raise TimeoutError("ComfyUI readiness exceeded three minutes")
        schema_response = provider.client.get("/object_info")
        schema_response.raise_for_status()
        schema = schema_response.json()
        with (ROOT / "workflow.json").open(encoding="utf-8") as source:
            bundle = json.load(source)
        for node in bundle["prompt"].values():
            if node["class_type"] not in schema:
                raise RuntimeError("Audited workflow node missing from live object_info")
        publish("object-info.json", schema)
        diagnostics.update(cuda_verified=True, schema_verified=True, model_sizes_verified=True)
        diagnostics["peak_device_used_bytes"] = 0
        publish("preflight.json", diagnostics)
        while True:
            free, total = torch.cuda.mem_get_info()
            diagnostics["peak_device_used_bytes"] = max(diagnostics["peak_device_used_bytes"], total - free)
            publish("heartbeat.json", {**diagnostics, "observed_at_unix": time.time()})
            if os.environ.get("ANIFLOW_MODE") == "generate":
                key = os.environ["ANIFLOW_REQUEST_KEY"]
                request = jobs.read(key, "request.json")
                if request and jobs.read(key, "result.json") is None:
                    if request.get("session_key") != session:
                        raise ValueError("Request belongs to a different stream session")
                    workflow = request["workflow"]
                    image = workflow[bundle["bindings"]["image"][0]]["inputs"][bundle["bindings"]["image"][1]]
                    if Path(image).name != image or "\\" in image:
                        raise ValueError("Unsafe first-frame name")
                    image_path = ROOT / "ComfyUI/input" / image
                    s3.download_file(bucket, f"{prefix}/inputs/{image}", str(image_path))
                    if hashlib.sha256(image_path.read_bytes()).hexdigest() != Path(image).stem:
                        raise ValueError("First-frame SHA256 mismatch")
                    # The S3 claim survives both browser and whole-session failure.
                    submitted = jobs.submit_once(key, workflow, provider, session)
                    import httpx
                    try:
                        prompt_id, state, history = provider.inspect(submitted.get("prompt_id"), key)
                    except httpx.HTTPError:
                        time.sleep(2)
                        continue
                    if state == "failed":
                        jobs.create_once(key, "failed.json", {"state": "failed", "prompt_id": prompt_id})
                        return
                    if history:
                        persist_video(s3, jobs, key, history, diagnostics)
                        return
            time.sleep(2)
    except Exception as exc:
        diagnostics.update(error_class=type(exc).__name__, error=str(exc)[:300])
        publish("preflight-failed.json", diagnostics)
        if os.environ.get("ANIFLOW_MODE") == "generate":
            jobs.create_once(os.environ["ANIFLOW_REQUEST_KEY"], "failed.json",
                             {"state": "failed", "error_class": type(exc).__name__})
        raise
    finally:
        if server is not None:
            server.terminate()


def persist_video(s3, jobs, key, history, diagnostics):
    import av
    import torch

    candidates = [item for output in history.get("outputs", {}).values()
                  for values in output.values() if isinstance(values, list)
                  for item in values if isinstance(item, dict)
                  and str(item.get("filename", "")).endswith(".mp4")]
    if len(candidates) != 1:
        raise ValueError("Expected one MP4 in real ComfyUI history")
    item = candidates[0]
    output = (ROOT / "ComfyUI/output").resolve()
    path = (output / item.get("subfolder", "") / item["filename"]).resolve()
    if not path.is_relative_to(output) or item.get("type") != "output":
        raise ValueError("Output escapes the ComfyUI output directory")
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        frames = sum(1 for _ in container.decode(video=0))
        if (stream.width, stream.height, float(stream.average_rate)) != (800, 1376, 24.0) or frames < 124:
            raise ValueError("Generated source does not match the audited native format")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    object_key = jobs._key(key, "source.mp4")
    s3.upload_file(str(path), jobs.bucket, object_key,
                   ExtraArgs={"ServerSideEncryption": "AES256",
                              "Metadata": {"sha256": digest.hexdigest()}})
    jobs.create_once(key, "result.json", {"key": object_key, "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(), "frames": frames,
        "preflight_kernel_peak_torch_vram_bytes": torch.cuda.max_memory_allocated(),
        "peak_device_used_bytes": diagnostics["peak_device_used_bytes"],
        "vram_measurement": "device total minus free, sampled every two seconds; includes display/runtime",
        "diagnostics": diagnostics})


if __name__ == "__main__":
    # Keep a real application window visible while diagnostics/job work runs.
    import tkinter
    window = tkinter.Tk()
    window.title("AniFlow private H3 experiment")
    tkinter.Label(window, text="AniFlow H3 — private S3 persistence and fixed stop deadline").pack(padx=40, pady=40)
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    window.mainloop()
