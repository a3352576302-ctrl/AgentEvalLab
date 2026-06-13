"""
tests/test_runner.py — YAML Runner 测试

测试从 YAML 文件加载测试用例、执行 Agent、运行断言的全流程。
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.runner import load_yaml_case, run_case, CaseResult
from agentevallab.agent import RuleBasedAgent


# ============================================================
# YAML 加载测试
# ============================================================

class TestLoadYamlCase:
    """从 YAML 文件加载测试用例"""

    def test_加载单个用例文件(self):
        """从一个 YAML 文件加载一条用例 → 返回 dict"""
        yaml_content = """
id: "TEST-001"
name: "测试用例"
category: functional
input: "北京天气怎么样？"
expected:
  tool_sequence: ["weather"]
  final_answer_contains: ["北京"]
assertions:
  check_final_answer: true
  check_tool_sequence: true
  check_tool_params: false
tags: ["weather"]
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            tmp_path = f.name

        try:
            case = load_yaml_case(tmp_path)
            assert case["id"] == "TEST-001"
            assert case["input"] == "北京天气怎么样？"
            assert case["expected"]["tool_sequence"] == ["weather"]
            assert case["assertions"]["check_tool_params"] is False
        finally:
            os.unlink(tmp_path)

    def test_加载包含多工具串联的用例(self):
        """多工具串联场景的 YAML 加载"""
        yaml_content = """
id: "TEST-002"
name: "天气加穿搭"
category: functional
input: "北京今天多少度？35度穿什么衣服合适？"
expected:
  tool_sequence: ["weather", "knowledge"]
  tool_calls:
    - tool: "weather"
      params:
        city: "北京"
    - tool: "knowledge"
      params:
        query: "35度穿什么"
  final_answer_contains: ["北京"]
  max_rounds: 3
assertions:
  check_final_answer: true
  check_tool_sequence: true
  check_tool_params: true
tags: ["multi-tool"]
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            tmp_path = f.name

        try:
            case = load_yaml_case(tmp_path)
            assert case["id"] == "TEST-002"
            assert len(case["expected"]["tool_calls"]) == 2
            assert case["expected"]["tool_calls"][0]["tool"] == "weather"
        finally:
            os.unlink(tmp_path)


# ============================================================
# 单条用例执行测试
# ============================================================

class TestRunCase:
    """执行单条用例并返回评测结果"""

    @pytest.fixture
    def agent(self):
        return RuleBasedAgent()

    def test_执行计算用例_全部通过(self, agent):
        """'123*456 等于多少？' → 计算工具 + 断言通过"""
        case = {
            "id": "CASE-001",
            "name": "计算",
            "category": "functional",
            "input": "123*456 等于多少？",
            "expected": {
                "tool_sequence": ["calculator"],
                "tool_calls": [
                    {"tool": "calculator", "params": {"expression": "123*456"}}
                ],
                "final_answer_contains": ["56088"],
                "max_rounds": 2,
            },
            "assertions": {
                "check_final_answer": True,
                "check_tool_sequence": True,
                "check_tool_params": True,
                "check_max_rounds": True,
            },
        }
        result = run_case(case, agent)
        assert isinstance(result, CaseResult)
        assert result.case_id == "CASE-001"
        assert result.trajectory is not None
        assert result.report.all_passed is True

    def test_执行天气用例_全部通过(self, agent):
        """'北京天气怎么样？' → weather + 断言通过"""
        case = {
            "id": "CASE-002",
            "name": "天气",
            "category": "functional",
            "input": "北京今天天气怎么样？",
            "expected": {
                "tool_sequence": ["weather"],
                "final_answer_contains": ["北京"],
                "max_rounds": 2,
            },
            "assertions": {
                "check_final_answer": True,
                "check_tool_sequence": True,
                "check_tool_params": False,
            },
        }
        result = run_case(case, agent)
        assert result.report.all_passed is True

    def test_执行失败用例_断言失败(self, agent):
        """预期 calculator，但输入天气 → L2 应失败"""
        case = {
            "id": "CASE-FAIL",
            "name": "故意失败",
            "category": "functional",
            "input": "北京天气怎么样？",
            "expected": {
                "tool_sequence": ["calculator"],  # 故意写错预期！
                "final_answer_contains": ["不存在的关键词"],
            },
            "assertions": {
                "check_final_answer": True,
                "check_tool_sequence": True,
                "check_tool_params": False,
            },
        }
        result = run_case(case, agent)
        assert result.report.all_passed is False
        # L1 和 L2 都应该失败
        l1 = [r for r in result.report.results if r.level == "L1"][0]
        l2 = [r for r in result.report.results if r.level == "L2"][0]
        assert l1.passed is False
        assert l2.passed is False

    def test_轨迹被正确记录(self, agent):
        """执行后 trajectory 应包含工具调用和最终答案"""
        case = {
            "id": "CASE-003",
            "name": "知识查询",
            "category": "functional",
            "input": "什么是RAG？",
            "expected": {
                "tool_sequence": ["knowledge"],
                "final_answer_contains": ["检索增强"],
            },
            "assertions": {
                "check_final_answer": True,
                "check_tool_sequence": True,
                "check_tool_params": False,
            },
        }
        result = run_case(case, agent)
        assert result.trajectory.tool_names == ["knowledge"]
        assert "检索增强" in result.trajectory.final_answer

    def test_不存在的城市_工具失败但不崩溃(self, agent):
        """'火星天气' → Agent 尝试调 weather，失败但优雅处理"""
        case = {
            "id": "CASE-004",
            "name": "不存在城市",
            "category": "boundary",
            "input": "火星今天天气怎么样？",
            "expected": {
                "tool_sequence": ["weather"],
            },
            "assertions": {
                "check_final_answer": False,
                "check_tool_sequence": True,
                "check_tool_params": False,
            },
        }
        result = run_case(case, agent)
        # 工具序列应匹配（调用了 weather）
        assert result.report.all_passed is True
        # Agent 没有崩溃，有 final_answer
        assert len(result.trajectory.final_answer) > 0
