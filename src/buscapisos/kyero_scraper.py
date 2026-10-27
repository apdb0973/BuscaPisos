"""Kyero scraper (navegación Playwright + parse DOM)."""

from __future__ import annotations

import asyncio
import random
import re
from dataclasses import dataclass
from typing import ClassVar

from bs4 import BeautifulSoup, Tag
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from buscapisos.base_scraper import ScraperFactory
from buscapisos.models import Listing
from buscapisos.parsing import parse_price


class KyeroScraperError(Exception):
    """Base de errores del conector de Kyero."""


class KyeroTimeoutError(KyeroScraperError):
    """Timeout de navegación o espera de selector."""


class KyeroSelectorError(KyeroScraperError):
    """Selector requerido ausente en el DOM."""


class KyeroFieldError(KyeroScraperError):
    """Nodo presente pero vacío."""


@dataclass(frozen=True)
class KyeroSelectors:
    """Selectores del detalle de Kyero (inyectables; se afinan tras inspección real)."""
    title: str = "h1"
    price: str = ".price"
    reference: str = ".reference"


_URL_ID_RE = re.compile(r"/property/(\d+)")


@ScraperFactory.register
class KyeroScraper:
    source = "kyero"
    source_name = "kyero"
    domains: ClassVar[tuple[str, ...]] = ("kyero.com",)

    def __init__(
        self,
        selectors: KyeroSelectors | None = None,
        timeout_ms: int = 30_000,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
    ) -> None:
        self.selectors = selectors or KyeroSelectors()
        self.timeout_ms = timeout_ms
        self.min_delay = min_delay
        self.max_delay = max_delay

    # -- parse puro (sin I/O) ------------------------------------------------
    def parse(self, content: str, url: str) -> Listing:
        soup = BeautifulSoup(content, "lxml")

        title = self._text(soup, self.selectors.title)
        price = parse_price(self._text(soup, self.selectors.price))
        source_id = self._source_id(soup, url)

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
            await page.wait_for_selector(self.selectors.title, timeout=self.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise KyeroTimeoutError(
                f"timeout navegando/esperando selector en {url}"
            ) from exc

        # Pausa aleatoria post-carga para estabilizar el render JS.
        await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

        html = await page.content()
        return self.parse(html, url)

    # -- helpers -------------------------------------------------------------
    def _select_one(self, soup: BeautifulSoup, selector: str) -> Tag:
        node = soup.select_one(selector)
        if node is None:
            raise KyeroSelectorError(f"selector {selector!r} no encontrado")
        return node

    def _text(self, soup: BeautifulSoup, selector: str) -> str:
        node = self._select_one(soup, selector)
        text = node.get_text(" ", strip=True)
        if not text:
            raise KyeroFieldError(f"selector {selector!r} vacío")
        return text

    def _source_id(self, soup: BeautifulSoup, url: str) -> str:
        # 1) Referencia visible en la ficha; 2) fallback: id numérico de la URL.
        try:
            raw = self._text(soup, self.selectors.reference)
            value = raw.replace("Reference", "").replace("Referencia", "").strip(" :")
            if value:
                return value
        except KyeroScraperError:
            pass
        match = _URL_ID_RE.search(url)
        if match:
            return match.group(1)
        raise KyeroFieldError("no se pudo extraer la referencia de Kyero")
