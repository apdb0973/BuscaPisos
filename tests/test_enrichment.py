"""pytest suite for EnrichmentService (Phase 3.3)."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import respx

from buscapisos.enrichment import (
    CATASTRO_ENDPOINT,
    EnrichmentService,
    calculate_acquisition_cost,
    itp_rate,
)


# ---------------------------------------------------------------------------
# 1. Canarian ITP: normal 6.5%, auction 7%, habitual residence 4%
# ---------------------------------------------------------------------------
def test_itp_rate_normal_purchase_is_6_5_percent():
    assert itp_rate("inmovilla", is_habitual_residence=False) == Decimal("0.065")


def test_itp_rate_auction_is_7_percent():
    assert itp_rate("boe", is_habitual_residence=False) == Decimal("0.07")


def test_itp_rate_habitual_residence_is_4_percent_for_both_origins():
    assert itp_rate("inmovilla", is_habitual_residence=True) == Decimal("0.04")
    assert itp_rate("boe", is_habitual_residence=True) == Decimal("0.04")


def test_calculate_acquisition_cost_adds_itp():
    assert calculate_acquisition_cost(Decimal("100000"), "inmovilla") == Decimal("106500")
    assert calculate_acquisition_cost(Decimal("100000"), "boe") == Decimal("107000")
    assert (
        calculate_acquisition_cost(Decimal("100000"), "boe", is_habitual_residence=True)
        == Decimal("104000")
    )


# ---------------------------------------------------------------------------
# 2. Catastro geolocation -> Supabase RPC UPDATE (mocked with respx)
# ---------------------------------------------------------------------------
@respx.mock
async def test_geolocate_property_updates_location_via_rpc():
    respx.get(CATASTRO_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"x": -15.42, "y": 28.10})
    )

    client = MagicMock()
    client.rpc.return_value.execute = AsyncMock()

    service = EnrichmentService(client)
    try:
        await service.geolocate_property("prop-1", "3395804DS4639S0056RA")
    finally:
        await service.aclose()

    client.rpc.assert_called_once_with(
        "update_property_location",
        {"p_id": "prop-1", "x": -15.42, "y": 28.10},
    )
    client.rpc.return_value.execute.assert_awaited_once()
