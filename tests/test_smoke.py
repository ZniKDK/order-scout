"""Проверка, что пакет устанавливается и импортируется."""

import order_scout


def test_package_imports():
    assert order_scout.__version__ == "0.1.0"
