"""Unit tests for Module Registry."""
import pytest
from app.registry.store import ModuleRegistry
from superbase_sdk.schemas import ModuleManifest, ModuleCapability


def test_register_and_get():
    reg = ModuleRegistry()
    manifest = ModuleManifest(
        module_id="test_module",
        name="Test",
        capabilities=[
            ModuleCapability(intent="test", keywords=["test"]),
        ],
        port=9999,
    )
    reg.register(manifest)
    assert reg.get("test_module") is not None
    assert reg.get("nonexistent") is None


def test_list_all():
    reg = ModuleRegistry()
    reg.register(ModuleManifest(module_id="a", name="A"))
    reg.register(ModuleManifest(module_id="b", name="B"))
    assert len(reg.list_all()) == 2


def test_load_from_directory():
    """Test loading manifests from the modules directory."""
    import os
    modules_dir = os.path.join(os.path.dirname(__file__), "..", "modules")
    reg = ModuleRegistry()
    reg.load_from_directory(modules_dir)
    ids = {m.module_id for m in reg.list_all()}
    assert "echo" in ids
    assert "weather" in ids
