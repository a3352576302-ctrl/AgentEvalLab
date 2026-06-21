"""
agentevallab/model_registry.py — 模型注册表读写

从 config/models.yaml 加载模型配置，支持按别名查询。

使用方式：
    from agentevallab.model_registry import load_registry, get_model
    registry = load_registry()
    cfg = get_model("deepseek-chat")
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

# 默认注册表路径（相对于项目根目录）
DEFAULT_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "models.yaml"
)


@dataclass
class ModelConfig:
    """单个模型的完整配置。"""
    alias: str
    provider: str
    model: str
    base_url_env: str = ""
    api_key_env: str = ""
    default_base_url: str = ""
    supports_tool_calling: bool = True
    supports_json_mode: bool = False
    supports_vision: bool = False
    context_window: int | None = None
    input_price_per_1m: float | None = None
    output_price_per_1m: float | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ModelRegistry:
    """模型注册表。"""
    models: dict[str, ModelConfig] = field(default_factory=dict)

    def get(self, alias: str) -> ModelConfig | None:
        """按别名查找模型。"""
        return self.models.get(alias)

    def list_aliases(self) -> list[str]:
        """列出所有已注册模型别名。"""
        return sorted(self.models.keys())

    def list_models(self) -> list[ModelConfig]:
        """列出所有模型配置。"""
        return list(self.models.values())


def load_registry(path: str | None = None) -> ModelRegistry:
    """从 YAML 文件加载模型注册表。

    参数：
        path — YAML 文件路径，默认 config/models.yaml

    返回：
        ModelRegistry 实例
    """
    filepath = path or DEFAULT_REGISTRY_PATH
    registry = ModelRegistry()

    if not os.path.exists(filepath):
        return registry

    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "models" not in data:
        return registry

    for alias, cfg in data["models"].items():
        registry.models[alias] = ModelConfig(
            alias=alias,
            provider=cfg.get("provider", ""),
            model=cfg.get("model", alias),
            base_url_env=cfg.get("base_url_env", ""),
            api_key_env=cfg.get("api_key_env", ""),
            default_base_url=cfg.get("default_base_url", ""),
            supports_tool_calling=cfg.get("supports_tool_calling", True),
            supports_json_mode=cfg.get("supports_json_mode", False),
            supports_vision=cfg.get("supports_vision", False),
            context_window=cfg.get("context_window"),
            input_price_per_1m=cfg.get("input_price_per_1m"),
            output_price_per_1m=cfg.get("output_price_per_1m"),
            tags=cfg.get("tags", []),
        )

    return registry


def get_model(alias: str, path: str | None = None) -> ModelConfig | None:
    """按别名获取单个模型配置（便捷函数）。"""
    return load_registry(path).get(alias)
