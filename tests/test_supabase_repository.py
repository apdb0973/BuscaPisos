"""pytest suite for SupabaseListingRepository (Phases 2.3–3.2).

Covers the idempotent add() flow:
  1. New listing          -> INSERT properties, listings, price_history.
  2. Existing, no change   -> only UPDATE listings.
  3. Existing, price drop  -> UPDATE listings + INSERT price_history.
  4. Network/API failure   -> RepositoryError.
  5. Auction listing       -> route registral fields, omit None physical fields.
  6. Registral match       -> link new listing to an existing property.
  7. Fuzzy match           -> link a listing without registral data by physical features.
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from buscapisos.models import Listing
from buscapisos.repository_supabase import RepositoryError, SupabaseListingRepository

PROPERTY_ID = "11111111-1111-1111-1111-111111111111"
LISTING_ID = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def listing() -> Listing:
    return Listing(
        title="Piso en Las Palmas de Gran Canaria",
        price=Decimal("320000"),
        area=Decimal("115"),
        bedrooms=3,
        bathrooms=2,
        url="https://demo.inmovilla.com/ficha/12345",
        source_id="INV-12345",
        source="inmovilla",
    )


@pytest.fixture
def auction_listing() -> Listing:
    return Listing(
        title="Subasta judicial en Las Palmas de Gran Canaria",
        price=Decimal("75000"),
        area=None,
        bedrooms=None,
        bathrooms=None,
        url="https://subastas.boe.es/detalleSubasta?idSub=SUB-JA-2026-000123",
        source_id="SUB-JA-2026-000123",
        source="boe",
        cru="13032000012345",
        referencia_catastral="3395804DS4639S0056RA",
        auction_value=Decimal("150000"),
        minimum_bid=Decimal("75000"),
    )


def _response(data, error=None):
    return SimpleNamespace(data=data, error=error)


def _table_builder(*, select_rows=(), insert_rows=(), update_rows=(), insert_error=None, select_or_rows=None, select_fuzzy_rows=None):
    """Mock a PostgREST query builder supporting select/insert/update chains."""
    builder = MagicMock()
    or_rows = list(select_or_rows) if select_or_rows is not None else list(select_rows)
    fuzzy_rows = list(select_fuzzy_rows) if select_fuzzy_rows is not None else []

    # .select(...).eq(...).eq(...).execute()
    builder.select.return_value.eq.return_value.eq.return_value.execute = AsyncMock(
        return_value=_response(list(select_rows))
    )
    # .select(...).eq(...).execute()   (single registral field)
    builder.select.return_value.eq.return_value.execute = AsyncMock(
        return_value=_response(list(select_rows))
    )
    # .select(...).or_(...).execute()  (both registral fields)
    builder.select.return_value.or_.return_value.execute = AsyncMock(
        return_value=_response(or_rows)
    )
    # .select(...).eq(...).eq(...).gte(...).lte(...).execute()  (fuzzy match)
    builder.select.return_value.eq.return_value.eq.return_value.gte.return_value.lte.return_value.execute = AsyncMock(
        return_value=_response(fuzzy_rows)
    )
    # .insert({...}).execute()
    builder.insert.return_value.execute = AsyncMock(
        side_effect=insert_error,
        return_value=_response(list(insert_rows)),
    )
    # .update({...}).eq(...).execute()
    builder.update.return_value.eq.return_value.execute = AsyncMock(
        return_value=_response(list(update_rows))
    )
    return builder


def _client_with(builders):
    """Mock supabase client whose .table(name) returns a builder per table."""
    client = MagicMock()
    client.table.side_effect = lambda name: builders[name]
    return client


# ---------------------------------------------------------------------------
# 1. New listing: SELECT empty -> INSERT properties, listings, price_history
# ---------------------------------------------------------------------------
async def test_add_new_listing_inserts_property_listing_and_price_history(listing):
    listings_builder = _table_builder(select_rows=[], insert_rows=[{"id": LISTING_ID}])
    properties_builder = _table_builder(insert_rows=[{"id": PROPERTY_ID}])
    price_history_builder = _table_builder(
        insert_rows=[{"id": "33333333-3333-3333-3333-333333333333"}]
    )

    client = _client_with({
        "listings": listings_builder,
        "properties": properties_builder,
        "price_history": price_history_builder,
    })
    repo = SupabaseListingRepository(client)

    await repo.add(listing)

    # Sequential table accesses:
    # select listings -> fuzzy-select properties -> insert properties
    # -> insert listings -> insert price_history.
    assert client.table.call_args_list == [
        call("listings"),
        call("properties"),
        call("properties"),
        call("listings"),
        call("price_history"),
    ]

    property_payload = properties_builder.insert.call_args.args[0]
    assert property_payload["property_type"] == "other"
    assert property_payload["title"] == listing.title
    assert property_payload["area"] == "115"
    assert property_payload["bedrooms"] == 3
    assert property_payload["bathrooms"] == 2

    listing_payload = listings_builder.insert.call_args.args[0]
    assert listing_payload["property_id"] == PROPERTY_ID
    assert listing_payload["source"] == listing.source
    assert listing_payload["source_id"] == listing.source_id
    assert listing_payload["url"] == listing.url
    assert listing_payload["title"] == listing.title
    assert listing_payload["price"] == "320000"
    assert listing_payload["area"] == "115"
    assert listing_payload["bedrooms"] == 3
    assert listing_payload["bathrooms"] == 2

    history_payload = price_history_builder.insert.call_args.args[0]
    assert history_payload["listing_id"] == LISTING_ID
    assert history_payload["price"] == "320000"


# ---------------------------------------------------------------------------
# 2. Existing listing, unchanged price -> UPDATE listings only
# ---------------------------------------------------------------------------
async def test_add_existing_listing_without_price_change_only_updates(listing):
    listings_builder = _table_builder(
        select_rows=[{"id": LISTING_ID, "source_id": listing.source_id, "price": "320000"}],
        update_rows=[],
    )
    properties_builder = _table_builder()
    price_history_builder = _table_builder()

    client = _client_with({
        "listings": listings_builder,
        "properties": properties_builder,
        "price_history": price_history_builder,
    })
    repo = SupabaseListingRepository(client)

    await repo.add(listing)

    # UPDATE listings with the current data, keyed by id.
    update_payload = listings_builder.update.call_args.args[0]
    assert update_payload["url"] == listing.url
    assert update_payload["title"] == listing.title
    assert update_payload["price"] == "320000"
    assert update_payload["area"] == "115"
    assert update_payload["bedrooms"] == 3
    assert update_payload["bathrooms"] == 2
    assert listings_builder.update.return_value.eq.call_args == call("id", LISTING_ID)

    # No new property, listing or price-history rows.
    properties_builder.insert.assert_not_called()
    listings_builder.insert.assert_not_called()
    price_history_builder.insert.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Existing listing, price drop -> UPDATE listings + INSERT price_history
# ---------------------------------------------------------------------------
async def test_add_existing_listing_with_price_drop_updates_and_inserts_history(listing):
    listings_builder = _table_builder(
        select_rows=[{"id": LISTING_ID, "source_id": listing.source_id, "price": "350000"}],
        update_rows=[],
    )
    properties_builder = _table_builder()
    price_history_builder = _table_builder(
        insert_rows=[{"id": "44444444-4444-4444-4444-444444444444"}]
    )

    client = _client_with({
        "listings": listings_builder,
        "properties": properties_builder,
        "price_history": price_history_builder,
    })
    repo = SupabaseListingRepository(client)

    await repo.add(listing)

    # UPDATE listings happened.
    assert listings_builder.update.called

    # A price_history row records the new (lower) price.
    history_payload = price_history_builder.insert.call_args.args[0]
    assert history_payload["listing_id"] == LISTING_ID
    assert history_payload["price"] == "320000"

    # No new property or listing rows.
    properties_builder.insert.assert_not_called()
    listings_builder.insert.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Network/API failure on the first write -> RepositoryError
# ---------------------------------------------------------------------------
async def test_add_raises_repository_error_when_property_insert_fails(listing):
    listings_builder = _table_builder(select_rows=[])  # new-listing path
    properties_builder = _table_builder(insert_error=Exception("connection refused"))
    price_history_builder = _table_builder()

    client = _client_with({
        "listings": listings_builder,
        "properties": properties_builder,
        "price_history": price_history_builder,
    })
    repo = SupabaseListingRepository(client)

    with pytest.raises(RepositoryError):
        await repo.add(listing)

    # Nothing else may run after the failing properties insert.
    listings_builder.insert.assert_not_called()
    price_history_builder.insert.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Auction listing: route registral fields to properties, omit None fields
# ---------------------------------------------------------------------------
async def test_add_auction_listing_routes_registral_fields_and_omits_nones(auction_listing):
    listings_builder = _table_builder(select_rows=[], insert_rows=[{"id": LISTING_ID}])
    properties_builder = _table_builder(insert_rows=[{"id": PROPERTY_ID}])
    price_history_builder = _table_builder(
        insert_rows=[{"id": "55555555-5555-5555-5555-555555555555"}]
    )

    client = _client_with({
        "listings": listings_builder,
        "properties": properties_builder,
        "price_history": price_history_builder,
    })
    repo = SupabaseListingRepository(client)

    await repo.add(auction_listing)

    # Registral identifiers are routed into the properties insert.
    property_payload = properties_builder.insert.call_args.args[0]
    assert "cru" in property_payload
    assert property_payload["cru"] == auction_listing.cru
    assert "referencia_catastral" in property_payload
    assert property_payload["referencia_catastral"] == auction_listing.referencia_catastral

    # The listings insert keeps price but omits the None physical fields.
    listing_payload = listings_builder.insert.call_args.args[0]
    assert "price" in listing_payload
    assert listing_payload["price"] == "75000"
    assert "area" not in listing_payload
    assert "bedrooms" not in listing_payload
    assert "bathrooms" not in listing_payload


# ---------------------------------------------------------------------------
# 6. New listing with existing registral data -> link to existing property
# ---------------------------------------------------------------------------
async def test_add_new_listing_with_existing_registral_data_links_to_existing_property(auction_listing):
    listings_builder = _table_builder(select_rows=[], insert_rows=[{"id": LISTING_ID}])
    properties_builder = _table_builder(select_or_rows=[{"id": "EXISTING-PROP-UUID"}])
    price_history_builder = _table_builder(
        insert_rows=[{"id": "66666666-6666-6666-6666-666666666666"}]
    )

    client = _client_with({
        "listings": listings_builder,
        "properties": properties_builder,
        "price_history": price_history_builder,
    })
    repo = SupabaseListingRepository(client)

    await repo.add(auction_listing)

    # properties was queried (not inserted) and the listing links to the existing id.
    assert client.table.call_args_list == [
        call("listings"),
        call("properties"),
        call("listings"),
        call("price_history"),
    ]

    # No new property row is created.
    properties_builder.insert.assert_not_called()

    # The listing is linked to the existing property id.
    listing_payload = listings_builder.insert.call_args.args[0]
    assert listing_payload["property_id"] == "EXISTING-PROP-UUID"

    # Price history is recorded normally.
    history_payload = price_history_builder.insert.call_args.args[0]
    assert history_payload["listing_id"] == LISTING_ID
    assert history_payload["price"] == "75000"


# ---------------------------------------------------------------------------
# 7. New listing without registral data -> link via fuzzy match
# ---------------------------------------------------------------------------
async def test_add_new_listing_without_registral_data_links_via_fuzzy_match(listing):
    listings_builder = _table_builder(select_rows=[], insert_rows=[{"id": LISTING_ID}])
    properties_builder = _table_builder(select_fuzzy_rows=[{"id": "FUZZY-PROP-UUID"}])
    price_history_builder = _table_builder(
        insert_rows=[{"id": "77777777-7777-7777-7777-777777777777"}]
    )

    client = _client_with({
        "listings": listings_builder,
        "properties": properties_builder,
        "price_history": price_history_builder,
    })
    repo = SupabaseListingRepository(client)

    await repo.add(listing)

    # properties was fuzzy-matched (not inserted) and the listing links to it.
    assert client.table.call_args_list == [
        call("listings"),
        call("properties"),
        call("listings"),
        call("price_history"),
    ]

    properties_builder.insert.assert_not_called()

    listing_payload = listings_builder.insert.call_args.args[0]
    assert listing_payload["property_id"] == "FUZZY-PROP-UUID"

    history_payload = price_history_builder.insert.call_args.args[0]
    assert history_payload["listing_id"] == LISTING_ID
    assert history_payload["price"] == "320000"
