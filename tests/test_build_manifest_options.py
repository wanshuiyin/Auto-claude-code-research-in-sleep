"""build_manifest must carry the optional scheduler settings queue_manager reads."""

import importlib.util
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills" / "experiment-queue" / "scripts" / "build_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("build_manifest", MODULE_PATH)
build_manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_manifest)

GRID = {
    "project": "p",
    "cwd": "/work",
    "conda": "env",
    "phases": [{
        "name": "a",
        "grid": {"seed": [1, 2]},
        "template": {"id": "s${seed}", "cmd": "python t.py --seed ${seed}"},
    }],
}


def test_optional_scheduler_settings_reach_the_manifest():
    manifest = build_manifest.build(
        {**GRID, "conda_hook": "/opt/custom/bin/conda", "gpu_free_threshold_mib": 2000}
    )

    assert manifest["conda_hook"] == "/opt/custom/bin/conda"
    assert manifest["gpu_free_threshold_mib"] == 2000


def test_unset_settings_stay_absent():
    manifest = build_manifest.build(GRID)

    assert "conda_hook" not in manifest
    assert "gpu_free_threshold_mib" not in manifest
