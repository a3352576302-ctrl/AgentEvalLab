"""
tests/test_model_registry.py — 模型注册表测试
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agentevallab.model_registry import (
    ModelConfig,
    ModelRegistry,
    load_registry,
    get_model,
)


class TestModelConfig:
    """ModelConfig 数据结构"""

    def test_基本构造(self):
        cfg = ModelConfig(alias="test", provider="deepseek", model="deepseek-chat")
        assert cfg.alias == "test"
        assert cfg.provider == "deepseek"

    def test_默认值(self):
        cfg = ModelConfig(alias="x", provider="p", model="m")
        assert cfg.supports_tool_calling is True
        assert cfg.context_window is None
        assert cfg.tags == []


class TestModelRegistry:
    """ModelRegistry 操作"""

    def test_空注册表(self):
        reg = ModelRegistry()
        assert reg.get("nonexistent") is None
        assert reg.list_aliases() == []

    def test_添加和查询(self):
        reg = ModelRegistry()
        reg.models["test"] = ModelConfig(alias="test", provider="p", model="m")
        cfg = reg.get("test")
        assert cfg is not None
        assert cfg.provider == "p"

    def test_列别名(self):
        reg = ModelRegistry()
        reg.models["a"] = ModelConfig(alias="a", provider="pa", model="ma")
        reg.models["b"] = ModelConfig(alias="b", provider="pb", model="mb")
        assert reg.list_aliases() == ["a", "b"]


class TestLoadRegistry:
    """从 YAML 加载"""

    def test_加载真实models_yaml(self):
        reg = load_registry()
        # 至少有 deepseek-chat 和 minimax-m2
        assert reg.get("deepseek-chat") is not None
        assert reg.get("minimax-m2") is not None
        assert "deepseek-chat" in reg.list_aliases()

    def test_deepseek配置完整(self):
        cfg = get_model("deepseek-chat")
        assert cfg is not None
        assert cfg.provider == "deepseek"
        assert cfg.model == "deepseek-chat"
        assert cfg.default_base_url == "https://api.deepseek.com/v1"
        assert cfg.supports_tool_calling is True
        assert cfg.context_window == 64000

    def test_minimax配置完整(self):
        cfg = get_model("minimax-m2")
        assert cfg is not None
        assert cfg.provider == "minimax"
        assert cfg.supports_tool_calling is True

    def test_不存在的文件返回空注册表(self):
        reg = load_registry("/nonexistent/path.yaml")
        assert reg.list_aliases() == []

    def test_不存在的模型返回None(self):
        assert get_model("nonexistent-model") is None

    def test_空YAML返回空注册表(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("other: data\n")
            f.flush()
            reg = load_registry(f.name)
        os.unlink(f.name)
        assert reg.list_aliases() == []
