"""pytest suite for the Intelligence Sidebar (Phase 4.2)."""

import os
import pytest
from playwright.async_api import async_playwright

MOCK_PROPERTY = {
    "id": "prop-123",
    "title": "Piso en Las Palmas de Gran Canaria",
    "area": "115",
    "bedrooms": 3,
    "property_type": "apartment",
    "listings": [
        {
            "source": "inmovilla",
            "price": "320000",
            "url": "https://example.com/ficha/1",
            "price_history": [
                {"price": "325000", "observed_at": "2026-01-01T00:00:00Z"},
                {"price": "320000", "observed_at": "2026-02-01T00:00:00Z"},
            ],
        }
    ],
}


@pytest.mark.asyncio
async def test_sidebar_opens_on_marker_click_and_shows_property():
    html_path = f"file:///{os.path.abspath('frontend/index.html')}".replace("\\", "/")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        captured = {}

        async def handle_properties(route):
            captured["url"] = route.request.url
            await route.fulfill(json=[MOCK_PROPERTY])

        await page.route("**/rest/v1/properties**", handle_properties)

        await page.goto(html_path)

        # Inject test Supabase credentials (read lazily by sidebar.js).
        await page.evaluate(
            """() => {
                window.ENV = {
                    SUPABASE_URL: 'https://test.supabase.co',
                    SUPABASE_ANON_KEY: 'test-key'
                };
            }"""
        )

        await page.wait_for_selector(".leaflet-tile-pane", state="attached", timeout=5000)

        # Inject a marker bound to a property id.
        await page.evaluate(
            "window.BuscaPisosMap.addMarker(28.10, -15.42, 'Test property', 'prop-123')"
        )
        await page.wait_for_selector(".leaflet-marker-icon", state="attached", timeout=5000)

        # Simulate a click on the marker.
        await page.click(".leaflet-marker-icon")

        # Wait for the sidebar to render the property title.
        await page.wait_for_selector("#sidebar-content .property-title", state="attached", timeout=5000)

        # 1. The intercepted request uses the nested join.
        url = captured.get("url", "")
        assert "select=" in url
        assert "listings" in url
        assert "price_history" in url

        # 2. The sidebar slid into view.
        sidebar_class = await page.get_attribute("#sidebar", "class")
        assert "translate-x-0" in sidebar_class
        assert "translate-x-full" not in sidebar_class

        # 3. The property title is rendered.
        content_text = await page.text_content("#sidebar-content")
        assert "Piso en Las Palmas de Gran Canaria" in content_text

        await browser.close()
