"""Тесты одного шага постоянного процесса."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from order_scout import runner
from order_scout.cli import main
from order_scout.config import load_config
from order_scout.runner import tick
from order_scout.sources.demo import DemoSource
from order_scout.storage import Storage
from tests.test_sender import FakeSender

ROOT = Path(__file__).parent.parent
T0 = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)


class CountingSource(DemoSource):
    """Демо-источник, который считает, сколько раз его читали."""

    def __init__(self):
        super().__init__()
        self.reads = 0

    def parse(self, payload):
        self.reads += 1
        return super().parse(payload)


@pytest.fixture
def cfg():
    return load_config(ROOT / "config.example.yaml")


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "orders.db")


async def test_first_tick_collects_and_sends(storage, cfg):
    sender = FakeSender()
    async with httpx.AsyncClient() as client:
        last = await tick(storage, cfg, [DemoSource()], client, sender, T0, None, evaluate_rules=True)
    assert last == T0
    assert sender.sent
    assert storage.by_status("pending") == []


async def test_collect_only_after_interval(storage, cfg):
    source = CountingSource()
    sender = FakeSender()
    async with httpx.AsyncClient() as client:
        last = await tick(storage, cfg, [source], client, sender, T0, None)
        assert await tick(storage, cfg, [source], client, sender, T0 + timedelta(minutes=5), last) == T0
        assert source.reads == 1
        later = T0 + timedelta(minutes=15)
        assert await tick(storage, cfg, [source], client, sender, later, last) == later
        assert source.reads == 2


async def test_collect_error_does_not_stop_sending(storage, cfg, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("сбой")

    monkeypatch.setattr(runner, "collect_once", broken)
    sender = FakeSender()
    async with httpx.AsyncClient() as client:
        last = await tick(storage, cfg, [DemoSource()], client, sender, T0, None)
    assert last == T0


def test_run_without_env(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("CHAT_ID", raising=False)
    code = main(["run", "--config", str(ROOT / "config.example.yaml"), "--db", str(tmp_path / "o.db")])
    assert code == 2
    assert ".env.example" in capsys.readouterr().err
