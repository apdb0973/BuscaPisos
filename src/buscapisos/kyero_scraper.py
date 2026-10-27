"""Kyero scraper (navegación Playwright + parse JSON-LD)."""

from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any, ClassVar

from bs4 import BeautifulSoup
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from buscapisos.base_scraper import ScraperFactory
from buscapisos.models import Listing
from buscapisos.parsing import parse_price


class KyeroScraperError(Exception):
    """Base de errores del conector de Kyero."""


class KyeroTimeoutError(KyeroScraperError):
    """Timeout de navegación o espera del bloque JSON-LD."""


class KyeroFieldError(KyeroScraperError):
    """Falta JSON-LD o no se pudo extraer la referencia."""


_URL_ID_RE = re.compile(r"/property/(\d+)")
_JSON_LD_SELECTOR = "script[type='application/ld+json']"


@ScraperFactory.register
class KyeroScraper:
    source = "kyero"
    source_name = "kyero"
    domains: ClassVar[tuple[str, ...]] = ("kyero.com",)

    def __init__(
        self,
        timeout_ms: int = 30_000,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.min_delay = min_delay
        self.max_delay = max_delay

    # -- parse puro (sin I/O) ------------------------------------------------
    def parse(self, content: str, url: str) -> Listing:
        soup = BeautifulSoup(content, "lxml")

        ld = self._extract_json_ld(soup)
        if ld is None:
            raise KyeroFieldError("no se encontró JSON-LD con nombre y precio")

        title = ld["name"]
        price = parse_price(str(ld["price"]))
        source_id = self._source_id(url)

        return Listing(
            title=title,
            price=price,
            area=None,
            bedrooms=None,
            bathrooms=None,
            url=url,
            source_id=source_id,
            source="kyero",
        )

    # -- navegación (Playwright) ---------------------------------------------
    async def scrape(self, page: Page, url: str) -> Listing:
        # Pausa aleatoria pre-navegación para espaciar peticiones.
        await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            # El JSON-LD aparece cuando el render SEO está listo.
            await page.wait_for_selector(_JSON_LD_SELECTOR, timeout=self.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise KyeroTimeoutError(
                f"timeout navegando/esperando JSON-LD en {url}"
            ) from exc

        # Pausa aleatoria post-carga para estabilizar el render JS.
        await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

        html = await page.content()
        return self.parse(html, url)

    # -- helpers -------------------------------------------------------------
    def _extract_json_ld(self, soup: BeautifulSoup) -> dict | None:
        """Devuelve {name, price} del primer bloque JSON-LD con nombre y precio."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            for item in self._iter_json_ld_items(data):
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                price = self._price_from_json_ld(item)
                if name and price is not None:
                    return {"name": str(name), "price": price}
        return None

    @staticmethod
    def _iter_json_ld_items(data: Any):
        if isinstance(data, dict):
            graph = data.get("@graph")
            if isinstance(graph, list):
                yield from graph
            else:
                yield data
        elif isinstance(data, list):
            yield from data

    @staticmethod
    def _price_from_json_ld(item: dict) -> Any:
        offers = item.get("offers")
        if isinstance(offers, dict):
            return offers.get("price")
        if isinstance(offers, list) and offers:
            return offers[0].get("price")
        return item.get("price")

    @staticmethod
    def _source_id(url: str) -> str:
        match = _URL_ID_RE.search(url)
        if match:
            return match.group(1)
        raise KyeroFieldError("no se pudo extraer la referencia de Kyero de la URL")
