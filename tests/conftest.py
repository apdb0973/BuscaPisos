"""Shared fixtures for the Inmovilla scraper test suite."""

import pytest

LISTING_URL = "https://demo.inmovilla.com/ficha/12345"


@pytest.fixture
def listing_url() -> str:
    return LISTING_URL


@pytest.fixture
def listing_html() -> str:
    """A representative Inmovilla property detail page (mocked DOM)."""
    return """
    <html>
      <body>
        <section id="fichapropiedad-titulos">
          <div class="fichapropiedad-tituloprincipal">
            <h1>Piso en Las Palmas de Gran Canaria</h1>
          </div>
        </section>
        <div class="fichapropiedad-bloqueprecio">
          <div class="fichapropiedad-precio">320.000 €</div>
        </div>
        <ul class="fichapropiedad-listadatos">
          <li><span class="caracteristica">Referencia </span><span class="valor">INV-12345</span></li>
          <li><span class="caracteristica">Superficie Construida</span><span class="valor">115 m2</span></li>
          <li><span class="caracteristica">Habitaciones</span><span class="valor">3</span></li>
          <li><span class="caracteristica">Baños</span><span class="valor">2</span></li>
        </ul>
      </body>
    </html>
    """


@pytest.fixture
def html_without_price() -> str:
    """Same page but the price selector has changed / is missing."""
    return """
    <html>
      <body>
        <section id="fichapropiedad-titulos">
          <div class="fichapropiedad-tituloprincipal">
            <h1>Piso sin precio</h1>
          </div>
        </section>
        <ul class="fichapropiedad-listadatos">
          <li><span class="caracteristica">Referencia </span><span class="valor">INV-00001</span></li>
          <li><span class="caracteristica">Superficie Construida</span><span class="valor">115 m2</span></li>
          <li><span class="caracteristica">Habitaciones</span><span class="valor">3</span></li>
          <li><span class="caracteristica">Baños</span><span class="valor">2</span></li>
        </ul>
      </body>
    </html>
    """


@pytest.fixture
def html_empty_price() -> str:
    """Same page but the price node exists yet is empty."""
    return """
    <html>
      <body>
        <section id="fichapropiedad-titulos">
          <div class="fichapropiedad-tituloprincipal">
            <h1>Piso con precio vacío</h1>
          </div>
        </section>
        <div class="fichapropiedad-bloqueprecio">
          <div class="fichapropiedad-precio"></div>
        </div>
        <ul class="fichapropiedad-listadatos">
          <li><span class="caracteristica">Referencia </span><span class="valor">INV-00002</span></li>
          <li><span class="caracteristica">Superficie Construida</span><span class="valor">115 m2</span></li>
          <li><span class="caracteristica">Habitaciones</span><span class="valor">3</span></li>
          <li><span class="caracteristica">Baños</span><span class="valor">2</span></li>
        </ul>
      </body>
    </html>
    """
