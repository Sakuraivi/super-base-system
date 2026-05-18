from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from .schemas import ModuleManifest, ModuleCapability


def load_manifest(path: str | Path) -> ModuleManifest:
    """从 YAML 文件加载 Module Manifest。"""
    with open(path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    return parse_manifest(raw)


def parse_manifest(raw: dict[str, Any]) -> ModuleManifest:
    """从 dict 解析 Module Manifest。"""
    mod = raw.get("module", raw)
    capabilities = [
        ModuleCapability(**cap) for cap in mod.get("capabilities", [])
    ]
    return ModuleManifest(
        module_id=mod["id"],
        name=mod.get("name", mod["id"]),
        version=mod.get("version", "0.1.0"),
        description=mod.get("description", ""),
        capabilities=capabilities,
        protocol=mod.get("interface", {}).get("protocol", "http"),
        port=mod.get("interface", {}).get("port", 8000),
        health_check_path=mod.get("interface", {}).get("health_check_path", "/health"),
        timeout_seconds=mod.get("runtime", {}).get("timeout_seconds", 120),
        supports_streaming=mod.get("runtime", {}).get("supports_streaming", False),
    )
