"""Unit tests for ConditionEvaluator."""
import pytest
from app.planner.condition_evaluator import ConditionEvaluator, ConditionEvalError


# ── 基本比较 ─────────────────────────────────────────────────────

def test_gt_true():
    assert ConditionEvaluator.evaluate("ctx.score > 80", {"score": 90}, {}) is True


def test_gt_false():
    assert ConditionEvaluator.evaluate("ctx.score > 80", {"score": 70}, {}) is False


def test_eq_string():
    assert ConditionEvaluator.evaluate("ctx.status == 'active'", {"status": "active"}, {}) is True


def test_eq_string_false():
    assert ConditionEvaluator.evaluate("ctx.status == 'active'", {"status": "inactive"}, {}) is False


def test_neq():
    assert ConditionEvaluator.evaluate("ctx.status != 'error'", {"status": "ok"}, {}) is True


def test_lt():
    assert ConditionEvaluator.evaluate("ctx.count < 10", {"count": 5}, {}) is True


def test_gte():
    assert ConditionEvaluator.evaluate("ctx.count >= 10", {"count": 10}, {}) is True


def test_lte():
    assert ConditionEvaluator.evaluate("ctx.count <= 10", {"count": 11}, {}) is False


# ── 布尔逻辑 ─────────────────────────────────────────────────────

def test_and_operator():
    assert ConditionEvaluator.evaluate(
        "ctx.age > 18 and ctx.verified == True",
        {"age": 25, "verified": True}, {},
    ) is True


def test_and_operator_false():
    assert ConditionEvaluator.evaluate(
        "ctx.age > 18 and ctx.verified == True",
        {"age": 25, "verified": False}, {},
    ) is False


def test_or_operator():
    assert ConditionEvaluator.evaluate(
        "ctx.role == 'admin' or ctx.role == 'editor'",
        {"role": "editor"}, {},
    ) is True


def test_not_operator():
    assert ConditionEvaluator.evaluate("not ctx.disabled", {"disabled": False}, {}) is True


def test_not_operator_false():
    assert ConditionEvaluator.evaluate("not ctx.disabled", {"disabled": True}, {}) is False


# ── contains / in ────────────────────────────────────────────────

def test_contains():
    assert ConditionEvaluator.evaluate(
        "ctx.tags contains 'urgent'", {"tags": ["urgent", "review"]}, {},
    ) is True


def test_contains_false():
    assert ConditionEvaluator.evaluate(
        "ctx.tags contains 'urgent'", {"tags": ["review"]}, {},
    ) is False


def test_in_operator():
    assert ConditionEvaluator.evaluate(
        "ctx.role in ['admin', 'editor']", {"role": "admin"}, {},
    ) is True


def test_in_operator_false():
    assert ConditionEvaluator.evaluate(
        "ctx.role in ['admin', 'editor']", {"role": "viewer"}, {},
    ) is False


# ── 结果引用 ─────────────────────────────────────────────────────

def test_results_reference():
    results = {"node_1": {"status": "completed"}}
    assert ConditionEvaluator.evaluate(
        "results.node_1.status == 'completed'", {}, results,
    ) is True


def test_results_reference_false():
    results = {"node_1": {"status": "failed"}}
    assert ConditionEvaluator.evaluate(
        "results.node_1.status == 'completed'", {}, results,
    ) is False


# ── 嵌套与复合 ──────────────────────────────────────────────────

def test_nested_attribute():
    assert ConditionEvaluator.evaluate(
        "ctx.config.debug == True", {"config": {"debug": True}}, {},
    ) is True


def test_chained_and_or():
    assert ConditionEvaluator.evaluate(
        "ctx.a > 0 and ctx.b > 0 or ctx.c == 'force'",
        {"a": 1, "b": -1, "c": "force"}, {},
    ) is True


# ── 安全性 ───────────────────────────────────────────────────────

def test_empty_expression():
    with pytest.raises(ConditionEvalError, match="Empty"):
        ConditionEvaluator.evaluate("", {}, {})


def test_none_expression():
    with pytest.raises(ConditionEvalError, match="Empty"):
        ConditionEvaluator.evaluate(None, {}, {})


def test_function_call_rejected():
    with pytest.raises(ConditionEvalError, match="not allowed|Unsupported"):
        ConditionEvaluator.evaluate("__import__('os').system('ls')", {}, {})


def test_import_rejected():
    with pytest.raises(ConditionEvalError, match="Syntax error"):
        ConditionEvaluator.evaluate("import os", {}, {})


def test_syntax_error():
    with pytest.raises(ConditionEvalError, match="Syntax error"):
        ConditionEvaluator.evaluate("ctx.score >", {"score": 5}, {})


def test_undefined_variable():
    with pytest.raises(ConditionEvalError):
        ConditionEvaluator.evaluate("ctx.missing > 0", {}, {})


def test_boolean_literal():
    assert ConditionEvaluator.evaluate("True", {}, {}) is True
    assert ConditionEvaluator.evaluate("False", {}, {}) is False
