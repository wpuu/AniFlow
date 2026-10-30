import hashlib
import json
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "infra/ec2/wan-workflow-bundle.template.json"
BUNDLE = json.loads(PATH.read_text(encoding="utf-8"))
GRAPH = BUNDLE["prompt"]
OUTPUTS = {
    "LoadImage": ("IMAGE", "MASK"), "ImageScale": ("IMAGE",), "UNETLoader": ("MODEL",),
    "CLIPLoader": ("CLIP",), "VAELoader": ("VAE",), "CLIPTextEncode": ("CONDITIONING",),
    "ModelSamplingSD3": ("MODEL",), "WanImageToVideo": ("CONDITIONING", "CONDITIONING", "LATENT"),
    "KSamplerAdvanced": ("LATENT",), "VAEDecode": ("IMAGE",), "CreateVideo": ("VIDEO",),
    "SaveVideo": ("VIDEO",),
}


def test_every_reference_targets_an_existing_output_and_graph_is_acyclic():
    edges = {}
    for key, node in GRAPH.items():
        edges[key] = []
        for value in node["inputs"].values():
            if isinstance(value, list):
                assert len(value) == 2 and value[0] in GRAPH and type(value[1]) is int
                outputs = OUTPUTS[GRAPH[value[0]]["class_type"]]
                assert 0 <= value[1] < len(outputs)
                edges[key].append(value[0])

    def walk(key, ancestors):
        assert key not in ancestors
        for dependency in edges[key]:
            walk(dependency, ancestors | {key})

    walk("16", set())


def test_all_nodes_feed_the_saved_result_without_acceleration_branches():
    reachable = set()

    def visit(key):
        reachable.add(key)
        for value in GRAPH[key]["inputs"].values():
            if isinstance(value, list):
                visit(value[0])

    visit("16")
    assert reachable == set(GRAPH)
    assert {n["class_type"] for n in GRAPH.values()} == set(OUTPUTS)
    assert all("lora" not in json.dumps(n).lower() for n in GRAPH.values())
    assert not any(n["class_type"] == "Wan22ImageToVideoLatent" for n in GRAPH.values())


@pytest.mark.parametrize("field", ["image", "prompt", "negative_prompt"])
def test_owner_bindings_preserve_placeholders_and_default_negative(field):
    key, name = BUNDLE["bindings"][field]
    value = GRAPH[key]["inputs"][name]
    if field != "negative_prompt":
        assert value.startswith("__REPLACE_WITH_") and value.endswith("__")
    if field == "image":
        assert GRAPH[key]["class_type"] == "LoadImage"
        assert GRAPH["2"]["inputs"]["image"] == [key, 0]
    else:
        assert GRAPH[key]["class_type"] == "CLIPTextEncode"
        conditioning = "negative" if field == "negative_prompt" else "positive"
        assert GRAPH["11"]["inputs"][conditioning] == [key, 0]


def test_14b_experts_and_text_encoder_keep_fp16_identity():
    high, low = GRAPH["3"]["inputs"], GRAPH["4"]["inputs"]
    assert high["unet_name"] == "wan2.2_i2v_high_noise_14B_fp16.safetensors"
    assert low["unet_name"] == "wan2.2_i2v_low_noise_14B_fp16.safetensors"
    assert high["weight_dtype"] == low["weight_dtype"] == "default"
    assert GRAPH["5"]["inputs"] == {"clip_name": "umt5_xxl_fp16.safetensors", "type": "wan", "device": "default"}
    assert GRAPH["6"]["inputs"]["vae_name"] == "wan_2.1_vae.safetensors"
    assert GRAPH["9"]["inputs"] == {"model": ["3", 0], "shift": 5.0}
    assert GRAPH["10"]["inputs"] == {"model": ["4", 0], "shift": 5.0}


def test_pinned_asset_manifest_covers_every_loader():
    assets = BUNDLE["preparation"]["models"]
    filenames = {Path(asset["relative_path"]).name for asset in assets}
    loaders = {value for node in GRAPH.values() for key, value in node["inputs"].items()
               if key in {"unet_name", "clip_name", "vae_name"}}
    assert filenames == loaders and len(assets) == 4
    assert sum(asset["bytes"] for asset in assets) == 68776044287
    assert all(len(asset["sha256"]) == 64 and int(asset["sha256"], 16) > 0 for asset in assets)


def test_expert_handoff_keeps_one_noise_source_and_twenty_steps():
    high, low = GRAPH["12"]["inputs"], GRAPH["13"]["inputs"]
    assert high["model"] == ["9", 0] and low["model"] == ["10", 0]
    assert high["latent_image"] == ["11", 2] and low["latent_image"] == ["12", 0]
    assert high["add_noise"] == "enable" and low["add_noise"] == "disable"
    assert high["return_with_leftover_noise"] == "enable"
    assert low["return_with_leftover_noise"] == "disable"
    assert high["start_at_step"] == 0
    assert high["end_at_step"] == low["start_at_step"] == 10
    assert low["end_at_step"] == high["steps"] == low["steps"] == 20
    for stage in (high, low):
        assert (stage["cfg"], stage["sampler_name"], stage["scheduler"]) == (3.5, "euler", "simple")
        assert stage["positive"] == ["11", 0] and stage["negative"] == ["11", 1]


def test_candidate_obeys_wan_grid_without_resizing_generated_video():
    inputs = GRAPH["11"]["inputs"]
    assert (inputs["width"], inputs["height"], inputs["length"], inputs["batch_size"]) == (800, 1376, 121, 1)
    assert inputs["width"] % 16 == inputs["height"] % 16 == 0
    assert (inputs["length"] - 1) % 4 == 0
    assert inputs["start_image"] == ["2", 0] and inputs["vae"] == ["6", 0]
    assert sum(n["class_type"] == "ImageScale" for n in GRAPH.values()) == 1
    assert GRAPH["14"]["inputs"] == {"samples": ["13", 0], "vae": ["6", 0]}
    assert GRAPH["15"]["inputs"]["images"] == ["14", 0]
    assert GRAPH["15"]["inputs"]["fps"] == 24


def test_crop_and_tail_trim_spec_is_exact_five_second_portrait():
    prep = BUNDLE["preparation"]
    source, final = prep["generated_target"], prep["final_target"]
    assert final["width"] * 16 == final["height"] * 9
    assert final["width"] >= 768 and final["height"] == source["height"]
    assert final["width"] + final["crop_x"] * 2 == source["width"]
    assert final["frames"] == source["frames"] - 1 == 120
    assert final["fps"] == source["fps"] == 24
    assert final["frames"] / final["fps"] == final["seconds"] == 5
    assert BUNDLE["postprocess"] == {"preset": "wan_native_5s_portrait_v1"}


def test_output_is_wan_mp4_and_never_mislabeled_h3():
    save = GRAPH["16"]["inputs"]
    assert BUNDLE["provider"] == "wan2.2-i2v-a14b"
    assert save["video"] == ["15", 0]
    assert save["filename_prefix"].startswith("aniflow/wan2_2_fp16/")
    assert save["format"] == "mp4" and save["format.codec"] == "h264"
    assert "h3" not in json.dumps(GRAPH).lower()


def test_source_pin_and_unverified_state_cannot_authorize_generation():
    prep = BUNDLE["preparation"]
    assert prep["source_sha256"] == "0bc0bee732181a0f5a5a0807b9e2cef883a1409bca4cdb70eca6b2e2e87e5c19"
    assert prep["source_workflow_commit"] in prep["source_workflow_url"]
    negative_sha = hashlib.sha256(GRAPH["8"]["inputs"]["text"].encode("utf-8")).hexdigest()
    assert negative_sha == prep["source_negative_prompt_sha256"] == "ce96e0324e4b54ce4b6e867f669ca520952e1a34cc116543516b1897f0d3c47e"
    assert prep["comfyui_commit"] in BUNDLE["source_url"]
    assert prep["status"] == "SOURCE_DERIVED_NOT_RUNTIME_VERIFIED"
    assert prep["source_default"] == {"width": 640, "height": 640, "frames": 81, "fps": 16}
    assert not any(prep[k] for k in ("quality_equivalent_to_h3_verified", "real_gpu_preflight_passed", "real_video_generated"))
    assert "actual_object_info" in prep["runtime_todo"]
    assert "launch_allowed" not in BUNDLE and "expires_at_unix" not in BUNDLE
