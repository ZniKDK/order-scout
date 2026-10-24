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


def test_evaluate_rules_after_demo(tmp_path, capsys):
    db = tmp_path / "orders.db"
    main(["collect", "--demo", "--config", str(EXAMPLE), "--db", str(db)])
    assert main(["evaluate", "--rules", "--config", str(EXAMPLE), "--db", str(db)]) == 0
    capsys.readouterr()
    main(["stats", "--db", str(db)])
    assert "evaluated: 4" in capsys.readouterr().out


def test_export_and_import_missing(tmp_path, capsys):
    db = tmp_path / "orders.db"
    main(["collect", "--demo", "--config", str(EXAMPLE), "--db", str(db)])
    out_file = tmp_path / "pending.json"
    assert main(["export", "--config", str(EXAMPLE), "--db", str(db), "--out", str(out_file)]) == 0
    assert out_file.exists()
    assert "выгружено: 4" in capsys.readouterr().out
    assert main(["import", "--db", str(db), "--file", str(tmp_path / "none.json")]) == 0
    assert "новых оценок нет" in capsys.readouterr().out


def test_missing_config(tmp_path, capsys):
    code = main(["collect", "--config", str(tmp_path / "nope.yaml"), "--db", str(tmp_path / "o.db")])
    assert code == 2
    assert "не найден" in capsys.readouterr().err
