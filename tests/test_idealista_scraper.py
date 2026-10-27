"""Tests for the Idealista scraper (pure DOM parsing, no network I/O)."""

from decimal import Decimal

import pytest

from buscapisos.idealista_scraper import (
    IdealistaFieldError,
    IdealistaScraper,
    IdealistaSelectorError,
)

LISTING_URL = "https://www.idealista.com/inmueble/103022283/"


@pytest.fixture
def listing_html() -> str:
    """A representative Idealista detail page (mocked DOM)."""
    return """
    <html>
      <body>
        <h1 class="main-info__title-main">Piso en venta en Las Palmas de Gran Canaria</h1>
        <span class="info-data-price">
          <span class="txt-bold">320.000</span>
          <span class="txt-suffix"> €</span>
        </span>
        <div class="ad-reference">Referencia: 103022283</div>
      </body>
    </html>
    """


def test_parse_extracts_title_price_and_reference(listing_html):
    listing = IdealistaScraper().parse(listing_html, LISTING_URL)

    assert listing.title == "Piso en venta en Las Palmas de Gran Canaria"
    assert listing.price == Decimal("320000")
    assert listing.source_id == "103022283"
    assert listing.source == "idealista"
    assert listing.url == LISTING_URL
    assert listing.area is None
    assert listing.bedrooms is None
    assert listing.bathrooms is None


def test_parse_falls_back_to_url_id_when_reference_missing():
    html = """
    <html>
      <body>
        <h1 class="main-info__title-main">Piso en venta en Telde</h1>
        <span class="info-data-price">150.000 €</span>
      </body>
    </html>
    """
    listing = IdealistaScraper().parse(
        html, "https://www.idealista.com/inmueble/99999999/"
    )

    assert listing.source_id == "99999999"
    assert listing.title == "Piso en venta en Telde"
    assert listing.price == Decimal("150000")


def test_parse_raises_when_price_selector_missing():
    html = """
    <html>
      <body>
        <h1 class="main-info__title-main">Piso en venta sin precio</h1>
      </body>
    </html>
    """
    with pytest.raises(IdealistaSelectorError):
        IdealistaScraper().parse(html, LISTING_URL)


def test_parse_raises_when_price_node_is_empty():
    html = """
    <html>
      <body>
        <h1 class="main-info__title-main">Piso en venta</h1>
        <span class="info-data-price"></span>
      </body>
    </html>
    """
    with pytest.raises(IdealistaFieldError):
        IdealistaScraper().parse(html, LISTING_URL)
