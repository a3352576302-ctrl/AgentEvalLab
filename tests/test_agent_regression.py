"""
tests/test_agent_regression.py — YAML 驱动的 Agent 回归测试

使用 pytest 参数化，自动将 test_cases/ 下每条 YAML 转换为一个测试用例。

运行方式：
    pytest tests/test_agent_regression.py -v     # 全部回归
    pytest tests/ -v                              # 包括单元测试 + 回归
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentevallab.runner import run_case


# ============================================================
# 参数化：从 conftest 的 all_yaml_cases 获取全部用例
# ============================================================

def pytest_generate_tests(metafunc):
    """动态生成测试参数：每条 YAML 对应一个 pytest case。"""
    if "yaml_case" in metafunc.fixturenames:
        # 加载全部 YAML
        from tests.conftest import CASE_DIR
        import glob
        from agentevallab.runner import load_yaml_case

        search_path = os.path.join(CASE_DIR, "**", "*.yaml")
        files = sorted(glob.glob(search_path, recursive=True))
        cases = []
        ids = []
        for filepath in files:
            try:
                case = load_yaml_case(filepath)
                cases.append(case)
                ids.append(case.get("id", os.path.basename(filepath)))
            except Exception as e:
                cases.append({
                    "id": os.path.basename(filepath),
                    "name": "加载失败",
                    "category": "error",
                    "input": "",
                    "expected": {},
                    "assertions": {},
                    "_load_error": str(e),
                })
                ids.append(os.path.basename(filepath))

        metafunc.parametrize(
            "yaml_case",
            cases,
            ids=ids,  # 每个 test case 显示为 YAML 的 id
        )


# ============================================================
# 回归测试
# ============================================================

def test_yaml_case(yaml_case, agent):
    """执行一条 YAML 用例，断言全部通过。

    - 如果 YAML 加载失败（_load_error），直接 FAIL
    - 否则执行 Agent + 断言，检查 report.all_passed
    """
    # YAML 加载失败
    if "_load_error" in yaml_case:
        pytest.fail(f"YAML 加载失败: {yaml_case['_load_error']}")

    # 执行用例
    result = run_case(yaml_case, agent)

    # 用例执行异常（非断言错误）
    if result.error:
        pytest.fail(f"用例执行异常: {result.error}")

    # 检查断言是否全部通过
    if not result.passed:
        # 构造详细的失败信息
        failed_assertions = [
            f"  [{r.level}] {r.name}: {r.reason}"
            for r in result.report.results
            if not r.passed
        ]
        detail = "\n".join(failed_assertions)
        pytest.fail(
            f"用例 [{result.case_id}] {result.case_name} 断言失败:\n{detail}"
        )
