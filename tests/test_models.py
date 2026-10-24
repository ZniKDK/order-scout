"""Тесты разбора сумм в рублях."""

from order_scout.models import parse_rub


def test_parse_rub_with_sign_and_space():
    assert parse_rub("1 500 ₽") == 150000


def test_parse_rub_with_nbsp():
    assert parse_rub("1 500") == 150000


def test_parse_rub_with_kopecks():
    assert parse_rub("1500.50") == 150050


def test_parse_rub_negotiable_is_none():
    assert parse_rub("по договорённости") is None


def test_parse_rub_empty_is_none():
    assert parse_rub("") is None
