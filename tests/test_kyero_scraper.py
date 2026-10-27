"""Tests for the Kyero scraper (JSON-LD parsing, no network I/O)."""

from decimal import Decimal

import pytest

from buscapisos.kyero_scraper import KyeroFieldError, KyeroScraper

LISTING_URL = (
    "https://www.kyero.com/en/property/20255271-villa-for-sale-alhaurin-de-la-torre"
)


@pytest.fixture
def listing_html() -> str:
    """A representative Kyero detail page with JSON-LD structured data."""
    return """
    <html>
      <body>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Product",
          "name": "Villa for sale in Alhaurin De La Torre, Malaga",
          "offers": {
            "@type": "Offer",
            "price": "365000",
            "priceCurrency": "EUR"
          }
        }
        </script>
      </body>
    </html>
    """


def test_parse_extracts_title_and_price_from_json_ld(listing_html):
    listing = KyeroScraper().parse(listing_html, LISTING_URL)

    assert listing.title == "Villa for sale in Alhaurin De La Torre, Malaga"
    assert listing.price == Decimal("365000")
    assert listing.source_id == "20255271"
    assert listing.source == "kyero"
    assert listing.url == LISTING_URL
    assert listing.area is None
    assert listing.bedrooms is None
    assert listing.bathrooms is None


def test_parse_handles_offers_as_list():
    html = """
    <html><body>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Apartment for sale in Marbella",
        "offers": [
          {"@type": "Offer", "price": "320000", "priceCurrency": "EUR"}
        ]
      }
      </script>
    </body></html>
    """
    listing = KyeroScraper().parse(
        html, "https://www.kyero.com/en/property/19362755-apartment-for-sale-marbella"
    )

    assert listing.title == "Apartment for sale in Marbella"
    assert listing.price == Decimal("320000")
    assert listing.source_id == "19362755"


def test_parse_handles_graph_array():
    html = """
    <html><body>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@graph": [
          {"@type": "Organization", "name": "Kyero"},
          {
            "@type": "Product",
            "name": "Villa in Camposol",
            "offers": {"@type": "Offer", "price": "219950", "priceCurrency": "EUR"}
          }
        ]
      }
      </script>
    </body></html>
    """
    listing = KyeroScraper().parse(
        html, "https://www.kyero.com/en/property/21532736-villa-for-sale-camposol"
    )

    assert listing.title == "Villa in Camposol"
    assert listing.price == Decimal("219950")
    assert listing.source_id == "21532736"


def test_parse_raises_when_json_ld_missing():
    html = """
    <html><body><h1>Sin JSON-LD</h1></body></html>
    """
    with pytest.raises(KyeroFieldError):
        KyeroScraper().parse(html, LISTING_URL)


def test_parse_raises_when_url_has_no_property_id():
    html = """
    <html><body>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Villa sin id",
        "offers": {"@type": "Offer", "price": "100000", "priceCurrency": "EUR"}
      }
      </script>
    </body></html>
    """
    with pytest.raises(KyeroFieldError):
        KyeroScraper().parse(html, "https://www.kyero.com/en/spain")
