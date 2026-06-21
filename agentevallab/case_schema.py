"""
agentevallab/case_schema.py — YAML 用例元数据校验

本模块定义测试用例的完整字段规范，并提供兼容读取：
- 旧 YAML 缺字段 → 自动填充默认值，不报错
- 新增字段全部可选，不破坏已有 46 条用例

使用方式：
    from agentevallab.case_schema import validate_case
    case = validate_case(yaml_dict)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ============================================================
# 字段默认值
# ============================================================

# 所有可选字段及其默认值
_FIELD_DEFAULTS: dict[str, Any] = {
    # 基础标识
    "id": "",
    "name": "",
    "description": "",
    "category": "unknown",
    # 场景分类
    "scene": "general",           # customer_service/coding/search/data_analysis/file_ops
    "difficulty": "medium",       # easy / medium / hard / adversarial
    "priority": "P1",             # P0 / P1 / P2
    # 标签
    "tags": [],
    # 输入
    "input": "",
    # 预期（兼容旧格式）
    "expected": {},
    # 断言开关
    "assertions": {},
    # 标准答案（用于人工参考，非自动断言）
    "golden_answer": "",
    "golden_tool_trace": [],      # [{tool, params, expected_result}]
    "expected_safe_behavior": "",  # 安全用例：描述期望的安全行为
    # 失败分类（标注这条用例最容易触发哪种失败）
    "failure_taxonomy": [],       # [TOOL_NOT_CALLED, PARAM_MISMATCH, ...]
    # 故障注入（兼容旧格式）
    "fault": None,
}

# 必填字段：缺一不可
_REQUIRED_FIELDS = ["id", "name", "input"]

# 合法值范围（用于警告，不强制）
_VALID_VALUES: dict[str, list[str]] = {
    "category": ["functional", "boundary", "error", "security", "unknown"],
    "scene": ["general", "customer_service", "coding", "search", "data_analysis", "file_ops", "security"],
    "difficulty": ["easy", "medium", "hard", "adversarial"],
    "priority": ["P0", "P1", "P2"],
}


# ============================================================
# 校验结果
# ============================================================

@dataclass
class SchemaResult:
    """校验结果。"""
    data: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


# ============================================================
# 校验函数
# ============================================================

def validate_case(raw: dict[str, Any]) -> SchemaResult:
    """校验并补全一条 YAML 用例。

    对于旧 YAML 中缺失的新字段，自动填充默认值。
    对于非法值，给出警告但不阻止加载。

    参数：
        raw — yaml.safe_load 返回的原始字典

    返回：
        SchemaResult，data 为补全后的用例字典
    """
    result = SchemaResult(data={})
    data = result.data  # 直接操作 result.data，避免引用分离

    # 1. 检查必填字段
    # 注意：空字符串是合法值（如边界用例 input: ""），不算缺失
    for key in _REQUIRED_FIELDS:
        if key not in raw or raw[key] is None:
            result.errors.append(f"缺少必填字段: '{key}'")
            data[key] = _FIELD_DEFAULTS.get(key, "")
        else:
            data[key] = raw[key]

    if result.errors:
        # 必填字段缺失，不继续校验，但返回已填充的数据
        return result

    # 2. 合并默认值：旧字段保留原值，新字段用默认值
    for key, default in _FIELD_DEFAULTS.items():
        if key in raw:
            data[key] = raw[key]
        elif key not in data:
            data[key] = default

    # 2b. 保留未在 _FIELD_DEFAULTS 中定义的额外字段（如 requires_llm）
    for key in raw:
        if key not in data:
            data[key] = raw[key]

    # 3. 深度合并 expected（保证子字段也有默认值）
    expected = data.get("expected", {})
    if not isinstance(expected, dict):
        result.warnings.append("expected 字段应为字典")
        expected = {}
        data["expected"] = expected
    expected.setdefault("tool_sequence", [])
    expected.setdefault("tool_calls", [])
    expected.setdefault("final_answer_contains", [])
    expected.setdefault("final_answer_contains_any", [])
    expected.setdefault("final_answer_not_contains", [])
    expected.setdefault("forbidden_tools", [])
    expected.setdefault("forbidden_patterns", [])
    expected.setdefault("max_rounds", None)
    expected.setdefault("max_latency_ms", None)
    expected.setdefault("max_total_tokens", None)

    # 4. 深度合并 assertions
    assertions = data.get("assertions", {})
    if not isinstance(assertions, dict):
        result.warnings.append("assertions 字段应为字典")
        assertions = {}
        data["assertions"] = assertions
    assertions.setdefault("check_final_answer", True)
    assertions.setdefault("check_tool_sequence", True)
    assertions.setdefault("check_tool_params", True)
    assertions.setdefault("check_max_rounds", True)
    assertions.setdefault("check_latency", False)
    assertions.setdefault("check_final_answer_not_contains", False)
    assertions.setdefault("check_forbidden_tools", False)
    assertions.setdefault("check_forbidden_patterns", False)
    assertions.setdefault("check_token_cost", False)

    # 5. 值合法性警告
    for field, valid_values in _VALID_VALUES.items():
        value = data.get(field)
        if value and value not in valid_values:
            result.warnings.append(
                f"'{field}' 值 '{value}' 不在推荐范围内: {valid_values}"
            )

    return result
