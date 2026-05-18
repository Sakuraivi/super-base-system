"""意图识别评估运行器。

用法:
    # Mock 模式评估（不需要 LLM API）
    INTENT_MODE=mock python evaluations/runners/intent_eval.py

    # Cloud 模式评估（需要 LLM API）
    INTENT_MODE=cloud python evaluations/runners/intent_eval.py
"""
from __future__ import annotations

import asyncio
import sys
import os
import time
from pathlib import Path

import yaml

# 添加 gateway 到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "gateway"))

from app.intent.router import IntentRouter
from app.registry.store import ModuleRegistry


def load_eval_dataset(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def run_evaluation():
    # 加载评估数据
    dataset_path = Path(__file__).resolve().parent.parent / "datasets" / "intent_eval.yaml"
    cases = load_eval_dataset(dataset_path)

    # 初始化 Registry + Router
    registry = ModuleRegistry()
    modules_dir = Path(__file__).resolve().parent.parent.parent / "modules"
    registry.load_from_directory(modules_dir)

    mode = os.getenv("INTENT_MODE", "mock")
    router = IntentRouter(mode=mode, registry=registry)

    print(f"=== Intent Router Evaluation (mode={mode}) ===\n")

    passed = 0
    failed = 0
    total_time = 0.0

    for i, case in enumerate(cases, 1):
        input_text = case["input"]
        expected = case["expected_module"]
        desc = case["description"]

        start = time.monotonic()
        result = await router.route(input_text)
        elapsed = time.monotonic() - start
        total_time += elapsed

        actual = result.module_id if result else None
        ok = actual == expected

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"  [{status}] Case {i}: {desc}")
        print(f"         Input:    {input_text}")
        print(f"         Expected: {expected}")
        print(f"         Actual:   {actual} (confidence={result.confidence if result else 'N/A'})")
        print(f"         Time:     {elapsed*1000:.0f}ms")
        if not ok:
            print(f"         >>> MISMATCH <<<")
        print()

    print(f"=== Results ===")
    print(f"  Mode:     {mode}")
    print(f"  Total:    {len(cases)}")
    print(f"  Passed:   {passed}")
    print(f"  Failed:   {failed}")
    print(f"  Accuracy: {passed/len(cases)*100:.1f}%")
    print(f"  Avg Time: {total_time/len(cases)*1000:.0f}ms")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_evaluation())
    sys.exit(0 if success else 1)
