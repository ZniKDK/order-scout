"""Источник FL.ru: RSS-лента последних заказов.

Бюджет есть только в заголовке: «… (Бюджет: 10 000 &#8381;)»,
иногда с припиской «, для всех». Числа откликов в ленте нет.
"""

import html
import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from order_scout.models import Order, parse_rub

log = logging.getLogger(__name__)

# Хвост заголовка с бюджетом: «(Бюджет: 500 ₽, для всех)»
_BUDGET_RE = re.compile(r"\s*\(Бюджет:\s*([^)]*)\)\s*$")
# Заказ без бюджета, но «для всех» (без ограничения на PRO): «… (для всех)»
_FOR_ALL_RE = re.compile(r"\s*\(для всех\)\s*$")
_ID_RE = re.compile(r"/projects/(\d+)")


class FlruSource:
    name = "flru"
    url = "https://www.fl.ru/rss/all.xml"

    def parse(self, payload: str) -> list[Order]:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as error:
            log.warning("FL.ru: не удалось разобрать RSS: %s", error)
            return []

        orders = []
        for item in root.iterfind("./channel/item"):
            link = (item.findtext("link") or "").strip()
            id_match = _ID_RE.search(link)
            if not id_match:
                continue
            # В CDATA сущности вроде &#8381; остаются текстом — раскодируем сами
            title = html.unescape(item.findtext("title") or "").strip()
            budget_kop = None
            budget_match = _BUDGET_RE.search(title)
            if budget_match:
                budget_kop = parse_rub(budget_match.group(1))
                title = title[: budget_match.start()].strip()
            title = _FOR_ALL_RE.sub("", title)
            pub_date = item.findtext("pubDate")
            orders.append(Order(
                source=self.name,
                external_id=id_match.group(1),
                url=link,
                title=title,
                description=html.unescape(item.findtext("description") or "").strip(),
                budget_kop=budget_kop,
                budget_max_kop=None,
                offers_count=None,
                created_at=parsedate_to_datetime(pub_date) if pub_date else None,
            ))
        return orders
