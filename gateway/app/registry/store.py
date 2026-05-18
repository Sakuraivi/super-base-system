from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from superbase_sdk.schemas import ModuleManifest, ModuleCapability
from ..config import settings


class ModuleRegistry:
    """模块注册中心：管理已注册的业务模块。"""

    def __init__(self):
        self._modules: dict[str, ModuleManifest] = {}

    def load_from_directory(self, base_dir: str | Path | None = None) -> None:
        """从模块目录扫描并加载所有 module_manifest.yaml。"""
        base = Path(base_dir or settings.modules_dir)
        if not base.exists():
            return
        for manifest_path in base.rglob("module_manifest.yaml"):
            try:
                manifest = self._parse_manifest_file(manifest_path)
                self._modules[manifest.module_id] = manifest
            except Exception as e:
                print(f"[Registry] Failed to load {manifest_path}: {e}")

    def register(self, manifest: ModuleManifest) -> None:
        self._modules[manifest.module_id] = manifest

    def get(self, module_id: str) -> ModuleManifest | None:
        return self._modules.get(module_id)

    def list_all(self) -> list[ModuleManifest]:
        return list(self._modules.values())

    def _parse_manifest_file(self, path: Path) -> ModuleManifest:
        with open(path, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f)

        mod = raw.get("module", raw)
        capabilities = [
            ModuleCapability(**cap) for cap in mod.get("capabilities", [])
        ]
        iface = mod.get("interface", {})
        runtime = mod.get("runtime", {})

        return ModuleManifest(
            module_id=mod["id"],
            name=mod.get("name", mod["id"]),
            version=mod.get("version", "0.1.0"),
            description=mod.get("description", ""),
            capabilities=capabilities,
            protocol=iface.get("protocol", "http"),
            port=iface.get("port", 8000),
            health_check_path=iface.get("health_check_path", "/health"),
            timeout_seconds=runtime.get("timeout_seconds", 120),
            supports_streaming=runtime.get("supports_streaming", False),
        )
