"""Тесты командной строки."""

from pathlib import Path

from order_scout.cli import main

EXAMPLE = Path(__file__).parent.parent / "config.example.yaml"


def test_collect_demo(tmp_path, capsys):
    db = tmp_path / "orders.db"
    code = main(["collect", "--demo", "--config", str(EXAMPLE), "--db", str(db)])
    assert code == 0
    assert "новых: 8, к оценке: 4, отсеяно: 4" in capsys.readouterr().out


def test_stats(tmp_path, capsys):
    db = tmp_path / "orders.db"
    main(["collect", "--demo", "--config", str(EXAMPLE), "--db", str(db)])
    capsys.readouterr()
    assert main(["stats", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "pending: 4" in out and "filtered_out: 4" in out


def test_missing_config(tmp_path, capsys):
    code = main(["collect", "--config", str(tmp_path / "nope.yaml"), "--db", str(tmp_path / "o.db")])
    assert code == 2
    assert "не найден" in capsys.readouterr().err
