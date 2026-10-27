"""Inmovilla scraper: Playwright navigation + in-memory DOM parsing (bs4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bs4 import BeautifulSoup, Tag
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from buscapisos.models import Listing
from buscapisos.parsing import parse_area, parse_int, parse_price
from buscapisos.base_scraper import ScraperFactory
from buscapisos.repository import ListingRepository


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------
class ScraperError(Exception):
    """Base class for all scraper failures."""


class ScraperTimeoutError(ScraperError):
    """Raised when Playwright navigation times out."""


class SelectorNotFoundError(ScraperError):
    """Raised when a required DOM selector is missing."""


class MissingFieldError(ScraperError):
    """Raised when a required node is present but empty."""


# ---------------------------------------------------------------------------
# Selectors (injectable: Inmovilla is a white-label engine, so the concrete
# CSS hooks vary per agency).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InmovillaSelectors:
    """Selectores del estándar Inmovilla (viviendascanarias.com y agencias afines)."""
    title: str = ".fichapropiedad-tituloprincipal h1"
    price: str = ".fichapropiedad-precio"
    characteristics_list: str = "ul.fichapropiedad-listadatos li"
    characteristic_label: str = ".caracteristica"
    characteristic_value: str = ".valor"


@ScraperFactory.register
class InmovillaScraper:
    """Navigates to a listing page and parses its DOM into a Listing.

    Navigation (Playwright) and DOM parsing (bs4) are strictly separated so the
    parser can be unit-tested against HTML fixtures without any network I/O.
    """

    source = "inmovilla"
    source_name = "inmovilla"
    domains: ClassVar[tuple[str, ...]] = ("inmovilla.com", "viviendascanarias.com", "canarinvest.com", "cardenas-grancanaria.com")

    def __init__(
        self,
        selectors: InmovillaSelectors | None = None,
        timeout_ms: int = 30_000,
    ) -> None:
        self.selectors = selectors or InmovillaSelectors()
        self.timeout_ms = timeout_ms

    # -- Pure DOM parsing (no I/O) -------------------------------------------
    def parse(self, html: str, url: str) -> Listing:
        soup = BeautifulSoup(html, "lxml")

        title = self._text(soup, self.selectors.title)
        price = parse_price(self._text(soup, self.selectors.price))

        characteristics = self._characteristics(soup)
        source_id = self._require_characteristic(characteristics, "Referencia")

        area_raw = (
            characteristics.get("Superficie Construida")
            or characteristics.get("Superficie parcela")
        )
        area = parse_area(area_raw) if area_raw else None
        bedrooms = (
            parse_int(characteristics["Habitaciones"])
            if characteristics.get("Habitaciones")
            else None
        )
        bathrooms = (
            parse_int(characteristics["Baños"])
            if characteristics.get("Baños")
            else None
        )

        return Listing(
            title=title,
            price=price,
            area=area,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            url=url,
            source_id=source_id,
            source="inmovilla",
        )

    # -- Network navigation (Playwright) -------------------------------------
    async def scrape(self, page: Page, url: str) -> Listing:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise ScraperTimeoutError(f"timeout navigating to {url}") from exc

        html = await page.content()
        return self.parse(html, url)

    # -- Internal helpers ----------------------------------------------------
    def _select_one(self, soup: BeautifulSoup, selector: str) -> Tag:
        node = soup.select_one(selector)
        if node is None:
            raise SelectorNotFoundError(f"selector {selector!r} not found")
        return node

    def _text(self, soup: BeautifulSoup, selector: str) -> str:
        node = self._select_one(soup, selector)
        text = node.get_text(" ", strip=True)
        if not text:
            raise MissingFieldError(f"selector {selector!r} produced empty text")
        return text

    def _characteristics(self, soup: BeautifulSoup) -> dict[str, str]:
        result: dict[str, str] = {}
        for li in soup.select(self.selectors.characteristics_list):
            label_el = li.select_one(self.selectors.characteristic_label)
            value_el = li.select_one(self.selectors.characteristic_value)
            if label_el is None or value_el is None:
                continue
            label = label_el.get_text(" ", strip=True)
            value = value_el.get_text(" ", strip=True)
            if label:
                result[label] = value
        return result

    @staticmethod
    def _require_characteristic(characteristics: dict[str, str], label: str) -> str:
        value = characteristics.get(label)
        if not value:
            raise MissingFieldError(f"característica {label!r} no encontrada")
        return value


class PipelineIngestor:
    """Orquestador genérico: resuelve el extractor por dominio y persiste.

    Recibe solo el repositorio; el scraper concreto se resuelve en tiempo de
    ejecución a partir del dominio de la URL mediante ScraperFactory.
    """

    def __init__(self, repository: ListingRepository) -> None:
        self.repository = repository

    async def ingest_html(self, html: str, url: str) -> Listing:
        scraper = ScraperFactory.create(url)
        listing = scraper.parse(html, url)
        await self.repository.add(listing)
        return listing

    async def ingest_url(self, page: Page, url: str) -> Listing:
        scraper = ScraperFactory.create(url)
        listing = await scraper.scrape(page, url)
        await self.repository.add(listing)
        return listing
