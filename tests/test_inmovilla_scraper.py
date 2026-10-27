"""pytest suite for the Inmovilla scraper (Phase 2.1).

Covers:
  1. Extraction + Pydantic validation from a mocked HTML fragment.
  2. Numeric cleaners (Spanish price / area / int formats).
  3. Error handling (changed selector / empty node).
  4. The Repository pattern via a mocked database.
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from buscapisos.models import Listing
from buscapisos.parsing import parse_area, parse_int, parse_price
from buscapisos.repository import InMemoryListingRepository
from buscapisos.scraper import (
    PipelineIngestor,
    InmovillaScraper,
    MissingFieldError,
    SelectorNotFoundError,
)


# ---------------------------------------------------------------------------
# 1. Extraction + Pydantic validation from the mocked HTML
# ---------------------------------------------------------------------------
def test_parse_listing_extracts_and_validates_all_fields(listing_html, listing_url):
    scraper = InmovillaScraper()

    listing = scraper.parse(listing_html, listing_url)

    # Pydantic returned a validated Listing with the correct concrete types.
    assert isinstance(listing, Listing)
    assert isinstance(listing.price, Decimal)
    assert isinstance(listing.area, Decimal)
    assert isinstance(listing.bedrooms, int)
    assert isinstance(listing.bathrooms, int)

    assert listing.title == "Piso en Las Palmas de Gran Canaria"
    assert listing.price == Decimal("320000")
    assert listing.area == Decimal("115")
    assert listing.bedrooms == 3
    assert listing.bathrooms == 2
    assert listing.url == listing_url
    assert listing.source_id == "INV-12345"
    assert listing.source == "inmovilla"


# ---------------------------------------------------------------------------
# 2. Numeric cleaners used before Pydantic
# ---------------------------------------------------------------------------
def test_numeric_parsers_clean_spanish_formats():
    assert parse_price("320.000 €") == Decimal("320000")
    assert parse_price("1.250.000 €") == Decimal("1250000")
    assert parse_price("320,50 €") == Decimal("320.50")

    assert parse_area("115 m²") == Decimal("115")
    assert parse_area("115 m2") == Decimal("115")
    assert parse_area("98,5 m2") == Decimal("98.5")

    assert parse_int("3 habitaciones") == 3
    assert parse_int("2 baños") == 2


# ---------------------------------------------------------------------------
# 3. Error handling (changed selector / empty node)
# ---------------------------------------------------------------------------
def test_parse_listing_raises_when_price_selector_missing(html_without_price, listing_url):
    scraper = InmovillaScraper()

    with pytest.raises(SelectorNotFoundError):
        scraper.parse(html_without_price, listing_url)


def test_parse_listing_raises_when_price_node_is_empty(html_empty_price, listing_url):
    scraper = InmovillaScraper()

    with pytest.raises(MissingFieldError):
        scraper.parse(html_empty_price, listing_url)


# ---------------------------------------------------------------------------
# 4. Repository pattern with a mocked database
# ---------------------------------------------------------------------------
async def test_ingestor_calls_repository_add_with_validated_listing(listing_html, listing_url):
    repo = AsyncMock()  # simulates the DB-backed repository

    ingestor = PipelineIngestor(repo)
    listing = await ingestor.ingest_html(listing_html, listing_url)

    repo.add.assert_awaited_once()
    saved = repo.add.await_args.args[0]
    assert saved == listing
    assert saved.price == Decimal("320000")
    assert saved.source_id == "INV-12345"


async def test_in_memory_repository_simulates_insertion(listing_html, listing_url):
    repo = InMemoryListingRepository()
    listing = InmovillaScraper().parse(listing_html, listing_url)

    await repo.add(listing)

    assert repo.count() == 1
    assert repo.all()[0] is listing
