"""Tests for the Kyero scraper (pure DOM parsing, no network I/O)."""

from decimal import Decimal

import pytest

from buscapisos.kyero_scraper import (
    KyeroFieldError,
    KyeroScraper,
    KyeroSelectorError,
)

LISTING_URL = (
    "https://www.kyero.com/en/property/20255271-villa-for-sale-alhaurin-de-la-torre"
)


@pytest.fixture
def listing_html() -> str:
    """A representative Kyero property detail page (mocked DOM)."""
    return """
    <html>
      <body>
        <h1>Villa for sale in Alhaurin De La Torre, Malaga</h1>
        <div class="price">€ 365,000</div>
        <div class="reference">Reference: VP-20255271</div>
      </body>
    </html>
    """


def test_parse_extracts_title_price_and_reference(listing_html):
    listing = KyeroScraper().parse(listing_html, LISTING_URL)

    assert listing.title == "Villa for sale in Alhaurin De La Torre, Malaga"
    assert listing.price == Decimal("365000")
    assert listing.source_id == "VP-20255271"
    assert listing.source == "kyero"
    assert listing.url == LISTING_URL
    assert listing.area is None
    assert listing.bedrooms is None
    assert listing.bathrooms is None


def test_parse_falls_back_to_url_id_when_reference_missing():
    html = """
    <html>
      <body>
        <h1>Apartment for sale in Marbella</h1>
        <div class="price">€ 320,000</div>
      </body>
    </html>
    """
    listing = KyeroScraper().parse(
        html, "https://www.kyero.com/en/property/19362755-apartment-for-sale-marbella"
    )

    assert listing.source_id == "19362755"
    assert listing.title == "Apartment for sale in Marbella"
    assert listing.price == Decimal("320000")


def test_parse_raises_when_price_selector_missing():
    html = """
    <html>
      <body>
        <h1>Apartment without price</h1>
      </body>
    </html>
    """
    with pytest.raises(KyeroSelectorError):
        KyeroScraper().parse(html, LISTING_URL)


def test_parse_raises_when_price_node_is_empty():
    html = """
    <html>
      <body>
        <h1>Apartment with empty price</h1>
        <div class="price"></div>
      </body>
    </html>
    """
    with pytest.raises(KyeroFieldError):
        KyeroScraper().parse(html, LISTING_URL)
