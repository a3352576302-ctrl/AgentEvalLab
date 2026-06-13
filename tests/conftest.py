"""
tests/conftest.py — pytest 共享 fixture

提供：
- agent  fixture：创建 RuleBasedAgent 实例
- all_yaml_cases fixture：加载 test_cases/ 下所有 YAML 用例
- pytest_generate_tests：自动参数化，每条 YAML 对应一个测试

使用方式：
    pytest tests/          → 自动加载 YAML 并运行全部
    pytest tests/ -k FUNC  → 只跑 functional 用例
"""
import os
import glob
import pytest
import sys

# 确保 agentevallab 可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentevallab.agent import RuleBasedAgent
from agentevallab.runner import load_yaml_case


# ============================================================
# 常量：测试用例目录
# ============================================================

CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "test_cases")


# ============================================================
# Fixture
# ============================================================

@pytest.fixture(scope="session")
def agent():
    """创建 RuleBasedAgent 实例（整个测试会话复用同一个）。"""
    return RuleBasedAgent()


@pytest.fixture(scope="session")
def all_yaml_cases():
    """加载 test_cases/ 下所有 YAML 文件，返回列表。

    每个元素为 (case_dict, filepath) 元组。
    """
    search_path = os.path.join(CASE_DIR, "**", "*.yaml")
    files = sorted(glob.glob(search_path, recursive=True))
    cases = []
    for filepath in files:
        try:
            case = load_yaml_case(filepath)
            cases.append((case, filepath))
        except Exception as e:
            # YAML 加载失败时，保留文件名和错误信息
            cases.append(({
                "id": os.path.basename(filepath),
                "name": "YAML 加载失败",
                "category": "error",
                "input": "",
                "expected": {},
                "assertions": {},
                "_load_error": str(e),
            }, filepath))
    return cases
