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


class TestRequiredMetadata:
    """所有用例必须有 scene / difficulty / priority"""

    def test_所有用例有scene(self):
        for c in _load_all():
            assert c.get("scene"), f"{c.get('id')} missing scene"

    def test_所有用例有difficulty(self):
        for c in _load_all():
            assert c.get("difficulty"), f"{c.get('id')} missing difficulty"

    def test_所有用例有priority(self):
        for c in _load_all():
            assert c.get("priority"), f"{c.get('id')} missing priority"


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


class TestCategoryWhitelist:
    """category 只能是合法值"""

    def test_category在白名单内(self):
        valid = {"functional", "boundary", "error", "security"}
        for c in _load_all():
            cat = c.get("category", "")
            assert cat in valid, \
                f"{c.get('id')}: category '{cat}' not in {valid}"


class TestSceneWhitelist:
    """scene 在白名单内"""

    def test_scene在白名单内(self):
        valid = {"general", "customer_service", "coding", "search",
                 "data_analysis", "file_ops", "security",
                 "multi_tool_planning", "rag_document_qa", "http_agent", "multi_turn"}
        for c in _load_all():
            scene = c.get("scene", "general")
            assert scene in valid, \
                f"{c.get('id')}: scene '{scene}' not in {valid}"


class TestSecurityCases:
    """安全用例规范"""

    def test_安全用例有expected_safe_behavior(self):
        for c in _load_all():
            if c.get("category") == "security":
                assert c.get("expected_safe_behavior"), \
                    f"{c.get('id')}: security case missing expected_safe_behavior"


class TestMultiToolCases:
    """多工具用例规范"""

    def test_多工具有tool_sequence(self):
        for c in _load_all():
            tags = c.get("tags", [])
            if "multi-tool" in tags or c.get("scene") == "multi_tool_planning":
                exp = c.get("expected", {})
                ts = exp.get("tool_sequence", [])
                assert len(ts) >= 2, \
                    f"{c.get('id')}: multi-tool case needs tool_sequence with >=2 tools, got {ts}"

    def test_多工具有max_rounds(self):
        for c in _load_all():
            tags = c.get("tags", [])
            if "multi-tool" in tags or c.get("scene") == "multi_tool_planning":
                exp = c.get("expected", {})
                mr = exp.get("max_rounds")
                assert mr is not None and mr >= 2, \
                    f"{c.get('id')}: multi-tool case needs max_rounds >=2, got {mr}"
