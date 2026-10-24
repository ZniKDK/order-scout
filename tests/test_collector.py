"""Тесты сборщика: обход источников, фильтр, ошибки сети."""

from pathlib import Path

import httpx
import pytest

from order_scout.collector import collect_once
from order_scout.config import load_config
from order_scout.sources.demo import DemoSource
from order_scout.sources.flru import FlruSource
from order_scout.sources.kwork import KworkSource
from order_scout.storage import Storage

ROOT = Path(__file__).parent.parent
KWORK_PAGE = (ROOT / "tests" / "fixtures" / "kwork_projects.html").read_text(encoding="utf-8")


@pytest.fixture
def cfg():
    return load_config(ROOT / "config.example.yaml")


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "orders.db")


async def test_demo_source_split(storage, cfg):
    async with httpx.AsyncClient() as client:
        report = await collect_once(storage, cfg, [DemoSource()], client)
    assert (report.new, report.pending, report.filtered) == (8, 4, 4)
    assert report.errors == []
    assert storage.counts() == {"pending": 4, "filtered_out": 4}


async def test_second_run_finds_nothing_new(storage, cfg):
    async with httpx.AsyncClient() as client:
        await collect_once(storage, cfg, [DemoSource()], client)
        report = await collect_once(storage, cfg, [DemoSource()], client)
    assert report.new == 0


def make_transport(flru_error: Exception | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if "fl.ru" in request.url.host:
            if flru_error:
                raise flru_error
            return httpx.Response(503)
        return httpx.Response(200, text=KWORK_PAGE)
    return httpx.MockTransport(handler)


async def test_one_source_down_others_collected(storage, cfg):
    async with httpx.AsyncClient(transport=make_transport()) as client:
        report = await collect_once(storage, cfg, [FlruSource(), KworkSource()], client)
    assert report.new == 3
    assert len(report.errors) == 1 and "flru" in report.errors[0]


class BrokenSource(DemoSource):
    """Источник, у которого разбор падает на неожиданных данных."""

    name = "broken"

    def parse(self, payload):
        raise KeyError("id")


async def test_parse_error_reported_others_collected(storage, cfg):
    async with httpx.AsyncClient() as client:
        report = await collect_once(storage, cfg, [BrokenSource(), DemoSource()], client)
    assert report.new == 8
    assert len(report.errors) == 1 and "broken" in report.errors[0]


async def test_several_kwork_pages_fetched_and_deduplicated(storage, cfg, monkeypatch):
    monkeypatch.setattr("order_scout.collector.PAGE_PAUSE_SEC", 0)
    seen_urls = []

    def handler(request):
        seen_urls.append(str(request.url))
        return httpx.Response(200, text=KWORK_PAGE)   # одинаковые страницы — заказы повторяются

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        report = await collect_once(storage, cfg, [KworkSource(category=11, pages=2)], client)
    assert seen_urls == ["https://kwork.ru/projects?c=11&page=1", "https://kwork.ru/projects?c=11&page=2"]
    assert report.new == 3


def test_make_sources_uses_config():
    from order_scout.collector import make_sources
    from order_scout.config import Config

    [kwork] = make_sources(["kwork"], Config(kwork_category=11, kwork_pages=4))
    assert len(kwork.urls) == 4 and "c=11" in kwork.urls[0]


async def test_timeout_is_reported_not_raised(storage, cfg):
    transport = make_transport(httpx.ReadTimeout("таймаут"))
    async with httpx.AsyncClient(transport=transport) as client:
        report = await collect_once(storage, cfg, [FlruSource(), KworkSource()], client)
    assert report.new == 3
    assert "flru" in report.errors[0]
