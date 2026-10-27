"""pytest suite for the Frontend PWA Map (Phase 4.1)."""

import os
import pytest
from playwright.async_api import async_playwright, expect

@pytest.mark.asyncio
async def test_leaflet_map_initialization():
    """Verify that the Leaflet map initializes, renders OSM tiles, and accepts markers."""
    # Build absolute path to the local HTML file
    html_path = f"file:///{os.path.abspath('frontend/index.html')}".replace("\\", "/")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Aísla el test de Supabase: devuelve lista vacía a loadProperties para
        # que no se pinten las propiedades reales cargadas desde config.js.
        async def handle_properties(route):
            await route.fulfill(json=[])

        await page.route("**/rest/v1/properties**", handle_properties)

        await page.goto(html_path)

        # 1. Assert #map container exists
        await expect(page.locator("#map")).to_be_visible()

        # 2. Assert Leaflet tile pane is injected (OSM/WMS layers added)
        tile_pane = page.locator(".leaflet-tile-pane")
        await expect(tile_pane).to_have_count(1, timeout=5000)

        # 3. Add a test marker via the exposed global API
        await page.evaluate(
            "window.BuscaPisosMap.addMarker(28.10, -15.42, 'Test property')"
        )

        # 4. Assert at least one marker icon is present
        markers = page.locator(".leaflet-marker-icon")
        await expect(markers).to_have_count(1, timeout=5000)

        await browser.close()
