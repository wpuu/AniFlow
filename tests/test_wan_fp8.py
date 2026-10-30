import copy
import importlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).parents[1]


@pytest.fixture
def profiles(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "infra/ec2"))
    return importlib.import_module("wan_fp8"), importlib.import_module("wan_bootstrap")


def original():
    return json.loads((ROOT / "infra/ec2/wan-workflow-bundle.template.json").read_text(encoding="utf-8"))


def test_builders_are_offline_pure_and_keep_fp16_default_strict(profiles, monkeypatch):
    fp8, base = profiles
    network, process = Mock(side_effect=AssertionError), Mock(side_effect=AssertionError)
    monkeypatch.setattr("socket.socket", network)
    monkeypatch.setattr("subprocess.run", process)
    source = original()
    before = copy.deepcopy(source)
    bundle = fp8.build_bundle(source)
    assert source == before
    with pytest.raises(ValueError, match="pinned FP16"):
        base.validate_bundle(bundle)
    with pytest.raises(ValueError, match="pinned FP16"):
        base.build_bootstrap(bundle)
    assert fp8.validate_manifest(base.validate_bundle(bundle, profile="fp8-scaled")) == fp8.build_manifest()
    assert base.validate_bundle(source)["models"] == source["preparation"]["models"]
    assert "profile" not in base.validate_bundle(source)
    network.assert_not_called()
    process.assert_not_called()


def test_exact_expert_pins_and_original_quality_are_preserved(profiles):
    fp8, base = profiles
    bundle = fp8.build_bundle()
    manifest = fp8.build_manifest()
    assert manifest["expected_total_bytes"] == 40209700367
    assert manifest["models"][2:] == original()["preparation"]["models"][2:]
    assert fp8.MANIFEST_FILENAME != "verified-models.json"
    assert bundle["preparation"]["manifest_filename"] == fp8.MANIFEST_FILENAME
    assert [(row["relative_path"], row["bytes"], row["sha256"])
            for row in manifest["models"]] == list(fp8.FP8_MODELS)
    assert bundle["prompt"]["3"]["inputs"]["weight_dtype"] == "default"
    expected = original()["prompt"]
    for node, data in bundle["prompt"].items():
        if node not in ("3", "4", "16"):
            assert data == expected[node]
    assert bundle["preparation"]["final_target"] == original()["preparation"]["final_target"]
    assert base.validate_bundle(original())["expected_total_bytes"] == 68776044287


@pytest.mark.parametrize("profile", [None, "fp8", "gguf-q6", "unknown", "FP8-SCALED"])
def test_unknown_profile_is_rejected(profiles, profile):
    fp8, base = profiles
    with pytest.raises(ValueError, match="Unknown Wan"):
        base.validate_bundle(fp8.build_bundle(), profile=profile)


@pytest.mark.parametrize("change", ["profile", "hash", "bytes", "t5", "precision", "steps", "resolution", "fps", "frames", "final", "audit", "postprocess"])
def test_fp8_identity_and_quality_changes_are_rejected(profiles, change):
    fp8, base = profiles
    bundle = fp8.build_bundle()
    if change == "profile":
        bundle["preparation"]["profile"] = "fp16"
    elif change == "hash":
        bundle["preparation"]["models"][0]["sha256"] = "0" * 64
    elif change == "bytes":
        bundle["preparation"]["models"][1]["bytes"] -= 1
    elif change == "t5":
        bundle["prompt"]["5"]["inputs"]["clip_name"] = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    elif change == "precision":
        bundle["prompt"]["3"]["inputs"]["weight_dtype"] = "fp8_e4m3fn_fast"
    elif change == "steps":
        bundle["prompt"]["12"]["inputs"]["steps"] = 4
    elif change == "resolution":
        bundle["prompt"]["11"]["inputs"]["width"] = 640
    elif change == "fps":
        bundle["prompt"]["15"]["inputs"]["fps"] = 16
    elif change == "frames":
        bundle["prompt"]["11"]["inputs"]["length"] = 81
    elif change == "final":
        bundle["preparation"]["final_target"]["width"] = 640
    elif change == "audit":
        bundle["preparation"]["manifest_filename"] = "verified-models.json"
    else:
        bundle["postprocess"]["preset"] = "unknown"
    with pytest.raises(ValueError, match="pinned FP8-SCALED"):
        base.validate_bundle(bundle, profile="fp8-scaled")


@pytest.mark.parametrize("change", ["profile", "hash", "extra", "revision"])
def test_manifest_rejects_tampering_and_premature_success_claims(profiles, change):
    fp8, _ = profiles
    manifest = fp8.build_manifest()
    if change == "hash":
        manifest["models"][0]["sha256"] = "0" * 64
    elif change == "extra":
        manifest["real_video_generated"] = True
    else:
        manifest[change] = "unknown"
    with pytest.raises(ValueError, match="fp8-scaled"):
        fp8.validate_manifest(manifest)


def test_fp16_bundle_rejects_unexpected_profile_even_with_original_weights(profiles):
    _, base = profiles
    bundle = original()
    bundle["preparation"]["profile"] = "fp8-scaled"
    with pytest.raises(ValueError, match="pinned FP16"):
        base.validate_bundle(bundle)
