"""Enrichment: Canarian fiscal engine + Catastro geolocation (Phase 3.3)."""

from __future__ import annotations

from decimal import Decimal

import httpx
from supabase import AsyncClient


# ---------------------------------------------------------------------------
# Canarian ITP (Impuesto de Transmisiones Patrimoniales)
# ---------------------------------------------------------------------------
ITP_RATE_GENERAL = Decimal("0.065")            # ordinary purchase
ITP_RATE_AUCTION = Decimal("0.07")             # auction (BOE)
ITP_RATE_HABITUAL_RESIDENCE = Decimal("0.04")  # habitual residence (bonus)
AUCTION_SOURCE = "boe"


def itp_rate(source: str, is_habitual_residence: bool = False) -> Decimal:
    """Return the Canarian ITP rate for a given source and destination."""
    if is_habitual_residence:
        return ITP_RATE_HABITUAL_RESIDENCE
    if source == AUCTION_SOURCE:
        return ITP_RATE_AUCTION
    return ITP_RATE_GENERAL


def calculate_acquisition_cost(
    price: Decimal,
    source: str,
    is_habitual_residence: bool = False,
) -> Decimal:
    """Total acquisition cost = price + ITP."""
    return price * (Decimal("1") + itp_rate(source, is_habitual_residence))


# ---------------------------------------------------------------------------
# Catastro geolocation
# ---------------------------------------------------------------------------
CATASTRO_ENDPOINT = (
    "https://ovc.catastro.meh.es/ovcservweb/OVCSWLocalizacionRC/"
    "OVCCoordenadas.asmx/Consulta_RCCOOR"
)


class EnrichmentError(Exception):
    """Raised when enrichment (geolocation) fails."""


class EnrichmentService:
    """Enriches saved properties with spatial (Catastro) data.

    The Supabase client is injected (dependency injection); the HTTP client is
    injected for tests and otherwise created/owned internally.

    The location update goes through the PostgREST RPC
    ``update_property_location(p_id, x, y)`` which wraps
    ``ST_SetSRID(ST_MakePoint(x, y), 4326)`` server-side: the Supabase client
    cannot inject PostGIS functions directly in an UPDATE payload.
    """

    def __init__(
        self,
        client: AsyncClient,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client
        self._http = http_client or httpx.AsyncClient()
        self._owns_http = http_client is None

    async def geolocate_property(
        self, property_id: str, referencia_catastral: str
    ) -> None:
        x, y = await self._fetch_coordinates(referencia_catastral)
        await self._update_location(property_id, x, y)

    async def _fetch_coordinates(
        self, referencia_catastral: str
    ) -> tuple[float, float]:
        response = await self._http.get(
            CATASTRO_ENDPOINT,
            params={"RC": referencia_catastral, "SRS": "EPSG:4326"},
        )
        response.raise_for_status()
        data = response.json()
        x = data.get("x")
        y = data.get("y")
        if x is None or y is None:
            raise EnrichmentError(f"catastro response missing coordinates: {data!r}")
        return float(x), float(y)

    async def _update_location(self, property_id: str, x: float, y: float) -> None:
        await self._client.rpc(
            "update_property_location",
            {"p_id": property_id, "x": x, "y": y},
        ).execute()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()
