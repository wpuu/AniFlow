"""Pure builders for the explicitly approved scaled-FP8 expert profile."""
import copy
import json
from pathlib import Path

from wan_bootstrap import COMFY_COMMIT, MODELS, WEIGHT_REVISION, validate_bundle

PROFILE = "fp8-scaled"
MANIFEST_FILENAME = "verified-models-fp8-scaled.json"
FP8_MODELS = (
    ("diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", 14294742832,
     "6122e79d55e0f235698d11d657f3b196c5273c830da00b2b013c5a048d5e6a42"),
    ("diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", 14294742832,
     "5471a457b6ac404202a5fbe6c11595a3d5641fc766b00f38763f72303fffc21e"),
    *MODELS[2:],
)


def build_manifest():
    """Return source pins only; this does not attest downloaded files or inference."""
    return {"schema_version": 1, "profile": PROFILE, "comfyui_commit": COMFY_COMMIT,
            "repository": "Comfy-Org/Wan-2.2", "revision": WEIGHT_REVISION,
            "expected_total_bytes": sum(row[1] for row in FP8_MODELS),
            "models": [{"relative_path": path, "bytes": size, "sha256": digest}
                       for path, size, digest in FP8_MODELS]}


def validate_manifest(manifest):
    """Reject altered profile, pins, order, model identities or success claims."""
    if manifest != build_manifest():
        raise ValueError("Manifest does not match the pinned fp8-scaled source contract")
    return copy.deepcopy(manifest)


def build_bundle(template=None):
    """Clone the audited FP16 template and change only the approved expert profile."""
    if template is None:
        template = json.loads((Path(__file__).parent / "wan-workflow-bundle.template.json")
                              .read_text(encoding="utf-8"))
    validate_bundle(template)
    bundle = copy.deepcopy(template)
    preparation = bundle["preparation"]
    preparation.update(profile=PROFILE, models=copy.deepcopy(build_manifest()["models"]),
        manifest_filename=MANIFEST_FILENAME,
        precision="Comfy-Org scaled-FP8 experts; original FP16 UMT5 and VAE unchanged. "
                  "Quantization is not numerically lossless; output quality remains unverified.",
        initial_memory_trial="Retained L4 with existing swap and fixed deadline; "
                             "actual memory fit, speed and video output require verification.")
    for node, row in zip(("3", "4"), FP8_MODELS[:2]):
        bundle["prompt"][node]["inputs"]["unet_name"] = row[0].split("/")[-1]
    bundle["prompt"]["16"]["inputs"]["filename_prefix"] = "aniflow/wan2_2_fp8_scaled/source121"
    validate_manifest(validate_bundle(bundle, profile=PROFILE))
    return bundle
