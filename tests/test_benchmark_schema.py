"""
tests/test_benchmark_schema.py — Benchmark 质量检查

验证 YAML 用例总数、ID 唯一、必填字段、分类数量一致。
"""
import sys
import os
import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
CASE_DIR = os.path.join(PROJECT_ROOT, "test_cases")


def _load_all():
    files = sorted(glob.glob(os.path.join(CASE_DIR, "**/*.yaml"), recursive=True))
    cases = []
    for fp in files:
        with open(fp, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            data["_filepath"] = fp
            cases.append(data)
    return cases


class TestCounts:
    """数量一致性"""

    def test_总数达标(self):
        cases = _load_all()
        assert len(cases) >= 300, f"expected >=300, got {len(cases)}"

    def test_generated数量(self):
        gen = [c for c in _load_all() if "generated" in c["_filepath"]]
        assert len(gen) >= 250, f"expected >=250 generated, got {len(gen)}"

    def test_category覆盖(self):
        cats = set(c.get("category") for c in _load_all())
        assert "functional" in cats
        assert "boundary" in cats
        assert "error" in cats
        assert "security" in cats


class TestUniqueIDs:
    """ID 唯一性"""

    def test_ID不重复(self):
        cases = _load_all()
        ids = [c.get("id", "") for c in cases]
        dups = [i for i in ids if ids.count(i) > 1]
        assert len(set(dups)) == 0, f"重复ID: {set(dups)}"


class TestRequiredFields:
    """必填字段"""

    def test_所有用例有id_name_input(self):
        for c in _load_all():
            assert c.get("id"), f"missing id in {c['_filepath']}"
            assert c.get("name"), f"missing name in {c['_filepath']}"
            assert c.get("input") is not None, f"missing input in {c['_filepath']}"


class TestRequiresLLM:
    """requires_llm 标记"""

    def test_数量达标(self):
        llm = [c for c in _load_all() if c.get("requires_llm")]
        assert len(llm) >= 200, f"expected >=200 requires_llm, got {len(llm)}"

    def test_LLM用例有原因(self):
        for c in _load_all():
            if c.get("requires_llm"):
                assert c.get("requires_llm_reason"), \
                    f"requires_llm but no reason in {c.get('id')}"
