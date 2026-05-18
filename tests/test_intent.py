"""Unit tests for Intent Router (mock mode)."""
import pytest
from app.intent.mock_classifier import MockClassifier


@pytest.fixture
def classifier():
    return MockClassifier()


def test_echo_intent(classifier):
    result = classifier.classify("你好世界")
    assert result is not None
    assert result.module_id == "echo"
    assert result.confidence > 0.9


def test_weather_intent(classifier):
    result = classifier.classify("今天北京天气怎么样")
    assert result is not None
    assert result.module_id == "weather"


def test_weather_temperature(classifier):
    result = classifier.classify("上海气温多少度")
    assert result is not None
    assert result.module_id == "weather"


def test_no_match(classifier):
    result = classifier.classify("写一首关于量子物理的诗")
    assert result is None


def test_ping_intent(classifier):
    result = classifier.classify("ping")
    assert result is not None
    assert result.module_id == "echo"
