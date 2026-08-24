"""Regression coverage for HTTP reviewer/provenance family alignment."""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import provenance as pv  # noqa: E402


def test_http_reviewer_families_are_recordable_in_provenance():
    assert pv.model_family("glm-5") == "zhipu"
    assert pv.model_family("zhipu/glm-4.5") == "zhipu"
    assert pv.model_family("mimo-v2") == "xiaomi"
    assert pv.model_family("xiaomi/mimo") == "xiaomi"
    assert pv.model_family("doubao-1.5-pro") == "bytedance"
    assert pv.model_family("volcengine/doubao") == "bytedance"


def test_provenance_family_matching_uses_boundaries():
    assert pv.model_family("ollama/deepseek-r1") == "deepseek"
    assert pv.model_family("meta/llama-3.3") == "meta"
    assert pv.model_family("claude-gpt-4") == "unknown"
