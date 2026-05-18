"""Tests for Complexity Classifier."""
import pytest
from app.intent.complexity import ComplexityClassifier
from superbase_sdk.schemas import Complexity


def test_simple():
    assert ComplexityClassifier.classify("你好世界") == Complexity.SINGLE
    assert ComplexityClassifier.classify("echo hello") == Complexity.SINGLE
    assert ComplexityClassifier.classify("北京天气") == Complexity.SINGLE


def test_pipeline():
    assert ComplexityClassifier.classify("分析代码并生成报告") == Complexity.PIPELINE
    assert ComplexityClassifier.classify("检查性能和修复问题") == Complexity.PIPELINE


def test_dag():
    assert ComplexityClassifier.classify("首先分析代码，然后修复问题") == Complexity.DAG
    assert ComplexityClassifier.classify("检查安全漏洞并同时分析性能") == Complexity.DAG


def test_model_selection():
    assert ComplexityClassifier.select_model(Complexity.SINGLE) is not None
    assert ComplexityClassifier.select_model(Complexity.DAG) is not None
