"""pytest suite for BoeConnector (Phase 2.4) — BOE/TGSS auction ingestion."""

from decimal import Decimal

import pytest

from buscapisos.boe_connector import BoeConnector
from buscapisos.models import Listing


@pytest.fixture
def auction_json() -> dict:
    """Simulated response from the BOE auctions API."""
    return {
        "id_subasta": "SUB-JA-2026-000123",
        "titulo": "Subasta judicial de inmueble en Las Palmas de Gran Canaria",
        "url": "https://subastas.boe.es/detalleSubasta?idSub=SUB-JA-2026-000123",
        "valor_subasta": 150000,
        "puja_minima": 75000,
        "referencia_catastral": "3395804DS4639S0056RA",
        "cru": "13032000012345",
        "provincia": "Las Palmas",
    }


# ---------------------------------------------------------------------------
# 1. The Listing model accepts the new fields without breaking the old ones.
# ---------------------------------------------------------------------------
def test_listing_model_accepts_auction_fields_without_breaking_existing():
    listing = Listing(
        title="Piso en Las Palmas de Gran Canaria",
        price=Decimal("75000"),
        area=Decimal("80"),
        bedrooms=3,
        bathrooms=2,
        url="https://example.com/ficha/1",
        source_id="INV-1",
        source="boe",
        cru="13032000012345",
        referencia_catastral="3395804DS4639S0056RA",
        auction_value=Decimal("150000"),
        minimum_bid=Decimal("75000"),
    )

    # New registral / auction fields are preserved.
    assert listing.cru == "13032000012345"
    assert listing.referencia_catastral == "3395804DS4639S0056RA"
    assert listing.auction_value == Decimal("150000")
    assert listing.minimum_bid == Decimal("75000")

    # Existing fields remain intact.
    assert listing.title == "Piso en Las Palmas de Gran Canaria"
    assert listing.price == Decimal("75000")
    assert listing.area == Decimal("80")
    assert listing.bedrooms == 3
    assert listing.bathrooms == 2
    assert listing.url == "https://example.com/ficha/1"
    assert listing.source_id == "INV-1"
    assert listing.source == "boe"


# ---------------------------------------------------------------------------
# 2. The connector parses the simulated JSON into a valid Listing.
# ---------------------------------------------------------------------------
def test_boe_connector_parses_auction_json(auction_json):
    listing = BoeConnector().parse(auction_json, auction_json["url"])

    assert isinstance(listing, Listing)
    assert listing.source == "boe"
    assert listing.source_id == "SUB-JA-2026-000123"

    # Auctions have no physical features.
    assert listing.area is None
    assert listing.bedrooms is None
    assert listing.bathrooms is None

    # Registral identifiers are filled.
    assert listing.cru == "13032000012345"
    assert listing.referencia_catastral == "3395804DS4639S0056RA"

    # Valuation / bid figures; price maps to the minimum bid.
    assert listing.auction_value == Decimal("150000")
    assert listing.minimum_bid == Decimal("75000")
    assert listing.price == Decimal("75000")

    # Title and URL come from the payload.
    assert listing.title == "Subasta judicial de inmueble en Las Palmas de Gran Canaria"
    assert listing.url == "https://subastas.boe.es/detalleSubasta?idSub=SUB-JA-2026-000123"


# ---------------------------------------------------------------------------
# 3. Resilience: missing id_subasta raises.
# ---------------------------------------------------------------------------
def test_boe_connector_raises_when_id_subasta_missing():
    with pytest.raises(ValueError):
        BoeConnector().parse({"valor_subasta": 100000, "puja_minima": 50000}, "https://subastas.boe.es/detalleSubasta?idSub=TEST")
