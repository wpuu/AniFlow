from importlib import import_module


def test_core_modules_import():
    for name in (
        "aniflow.cli",
        "aniflow.pipeline.episode",
        "aniflow.pipeline.segment",
        "aniflow.pipeline.keyframes",
        "aniflow.agnes.video",
        "aniflow.agnes.vision",
    ):
        assert import_module(name) is not None
