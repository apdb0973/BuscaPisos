"""Connector for BOE/TGSS auction portals (simulated JSON API, Phase 2.4)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from playwright.async_api import Page

from buscapisos.base_scraper import ScraperFactory
from buscapisos.models import Listing


@ScraperFactory.register
class BoeConnector:
    """Parses simulated auction-portal JSON into Listing objects.

    Unlike Inmovilla listings, auction edicts have no bedrooms/bathrooms/area,
    but carry registral identifiers (cru, referencia_catastral) and valuation /
    minimum-bid figures. `price` maps to the minimum bid (the actionable floor),
    falling back to the appraisal value when no minimum bid is present.
    """

    source = "boe"
    source_name = "boe"
    domains = ("subastas.boe.es", "boe.es")

    def parse(self, content: Any, url: str) -> Listing:
        payload = content
        source_id = self._require_source_id(payload)

        minimum_bid = self._to_decimal(payload.get("puja_minima"))
        auction_value = self._to_decimal(payload.get("valor_subasta"))
        price = minimum_bid if minimum_bid is not None else auction_value
        if price is None:
            raise ValueError("auction payload missing puja_minima and valor_subasta")

        title = str(payload.get("titulo") or self._build_title(payload, source_id))
        listing_url = str(url or payload.get("url") or self._build_url(source_id))

        return Listing(
            title=title,
            price=price,
            area=None,
            bedrooms=None,
            bathrooms=None,
            url=listing_url,
            source_id=source_id,
            source="boe",
            cru=payload.get("cru"),
            referencia_catastral=payload.get("referencia_catastral"),
            auction_value=auction_value,
            minimum_bid=minimum_bid,
        )

    async def scrape(self, page: Page, url: str) -> Listing:
        """Descarga el JSON de la URL y delega en parse(). No usa Playwright."""
        async with httpx.AsyncClient() as http:
            response = await http.get(url, follow_redirects=True)
            response.raise_for_status()
            return self.parse(response.json(), url)

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _require_source_id(payload: dict[str, Any]) -> str:
        value = payload.get("id_subasta")
        if not value:
            raise ValueError("auction payload missing id_subasta")
        return str(value)

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"cannot parse decimal from {value!r}") from exc

    @staticmethod
    def _build_title(payload: dict[str, Any], source_id: str) -> str:
        provincia = payload.get("provincia")
        if provincia:
            return f"Subasta {source_id} en {provincia}"
        return f"Subasta {source_id}"

    @staticmethod
    def _build_url(source_id: str) -> str:
        return f"https://subastas.boe.es/detalleSubasta?idSub={source_id}"
