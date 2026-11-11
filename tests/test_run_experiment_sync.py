"""Execute the documented SSH sync filters locally, without an SSH server."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("skill_root", ["skills", "skills/skills-codex"])
def test_documented_sync_preserves_runnable_project_and_excludes_other_files(
    tmp_path: Path, skill_root: str,
) -> None:
    rsync = shutil.which("rsync")
    if not rsync:
        pytest.skip("rsync is not installed")
    skill = (REPO / skill_root / "run-experiment/SKILL.md").read_text()
    blocks = re.findall(r"```bash\n(.*?)```", skill, re.S)
    command = next(block for block in blocks if block.startswith("rsync -avz --prune-empty-dirs"))
    argv = shlex.split(command.replace("\\\n", ""))
    assert argv[-2:] == ["<local_src>/", "<server>:<remote_dst>/"]

    source, destination = tmp_path / "local source", tmp_path / "remote destination"
    required = {
        "train.py": (
            "from toy.model import value\n"
            "import argparse,json\n"
            "p=argparse.ArgumentParser();p.add_argument('--config',required=True)\n"
            "config=json.load(open(p.parse_args().config))\n"
            "resource=json.load(open(config['vocab']))\n"
            "print(json.dumps({'result':value+config['offset'],'vocab':resource}))\n"
        ),
        "toy/__init__.py": "",
        "toy/model.py": "value=5\n",
        "configs/sanity.json": '{"offset":2,"vocab":"assets/vocab.json"}\n',
        "assets/vocab.json": '["token"]\n',
    }
    excluded = [
        ".env", ".git/internal.py", ".claude/settings.json", ".aris/private.py",
        "data/helper.py", "datasets/items.json", "weights/private.py",
        "checkpoints/loader.py", "outputs/result.py", "wandb/probe.py",
        "__pycache__/cached.py", "configs/private.json", "assets/large.bin",
        "venv/lib/site-packages/third_party.py", "env/lib/site-packages/third_party.py",
    ]
    for name, content in {**required, **dict.fromkeys(excluded, "must not sync\n")}.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    destination.mkdir()
    argv[0] = rsync
    argv[-2:] = [str(source) + "/", str(destination) + "/"]
    copied = subprocess.run(argv, text=True, capture_output=True)
    assert copied.returncode == 0, copied.stderr
    assert {str(path.relative_to(destination)) for path in destination.rglob("*") if path.is_file()} == set(required)
    executed = subprocess.run(
        [sys.executable, "-B", "train.py", "--config", "configs/sanity.json"],
        cwd=destination, text=True, capture_output=True,
    )
    assert executed.returncode == 0, executed.stderr
    assert json.loads(executed.stdout) == {"result": 7, "vocab": ["token"]}
