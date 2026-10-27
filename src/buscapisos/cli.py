"""Command-line entry point for the full ingestion pipeline (Phase 2.2).

Usage:
    python -m buscapisos.cli "https://<agencia>.inmovilla.com/ficha/..."

Requires SUPABASE_URL and SUPABASE_KEY (from the environment or a .env file).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from supabase import create_async_client

from buscapisos.boe_connector import BoeConnector  # noqa: F401  # registra el scraper BOE
from buscapisos.repository_supabase import RepositoryError, SupabaseListingRepository
from buscapisos.scraper import PipelineIngestor


async def _run(url: str, headless: bool) -> int:
    load_dotenv()

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        print("error: SUPABASE_URL and SUPABASE_KEY must be set (or in .env)", file=sys.stderr)
        return 1

    # Inyección de dependencias: el ingestor resuelve el scraper por dominio.
    client = await create_async_client(supabase_url, supabase_key)
    ingestor = PipelineIngestor(SupabaseListingRepository(client))

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            try:
                page = await browser.new_page()
                listing = await ingestor.ingest_url(page, url)
            finally:
                await browser.close()
    except RepositoryError as exc:
        print(f"error persisting listing: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # scraping / navigation failures
        print(f"error scraping {url}: {exc}", file=sys.stderr)
        return 3

    print(f"stored {listing.source_id!r} — {listing.title!r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="buscapisos",
        description="Scrape an Inmovilla listing URL and persist it to Supabase.",
    )
    parser.add_argument("url", help="URL of the listing page to scrape")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="run the browser in headed mode (default: headless)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.url, headless=not args.headed))


if __name__ == "__main__":
    raise SystemExit(main())
