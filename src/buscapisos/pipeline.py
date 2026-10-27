"""pipeline.py — Orquestación del pipeline: ingesta + enriquecimiento + alertas.

Ejecución:
    python -m buscapisos.pipeline --urls urls.txt
    python -m buscapisos.pipeline --url "https://..."

Variables de entorno (o .env):
    SUPABASE_URL               -> Project URL
    SUPABASE_SERVICE_ROLE_KEY  -> clave service_role (maestra, backend)
    TELEGRAM_BOT_TOKEN         -> token del bot de Telegram (opcional, para alertas)
    TELEGRAM_CHAT_ID           -> id del chat destino en Telegram (opcional)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from decimal import Decimal

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from supabase import AsyncClient, create_async_client

from buscapisos.alert_engine import (
    Alert,
    AlertEngine,
    ListingSnapshot,
    PricePoint,
    PropertySnapshot,
)
from buscapisos.boe_connector import BoeConnector  # noqa: F401  (registra el scraper BOE)
from buscapisos.enrichment import EnrichmentService
from buscapisos.idealista_scraper import IdealistaScraper  # noqa: F401  (registra Idealista)
from buscapisos.notifier import TelegramNotifier
from buscapisos.repository_supabase import SupabaseListingRepository
from buscapisos.scraper import InmovillaScraper, PipelineIngestor  # noqa: F401  (registra Inmovilla)

# Lista temporal de respaldo (se usa si no hay --url ni urls.txt).
DEFAULT_URLS: list[str] = []


def _parse_dt(value) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _read_urls(args: argparse.Namespace) -> list[str]:
    if args.url:
        return [args.url]
    if args.urls and os.path.exists(args.urls):
        with open(args.urls, encoding="utf-8") as fh:
            return [
                line.strip()
                for line in fh
                if line.strip() and not line.lstrip().startswith("#")
            ]
    return list(DEFAULT_URLS)


class Pipeline:
    """Orquesta ingesta -> enriquecimiento -> alertas con dependencias inyectadas."""

    def __init__(
        self,
        ingestor: PipelineIngestor,
        enrichment: EnrichmentService,
        alert_engine: AlertEngine,
        client: AsyncClient,
        notifier: TelegramNotifier | None = None,
    ) -> None:
        self.ingestor = ingestor
        self.enrichment = enrichment
        self.alert_engine = alert_engine
        self.client = client
        self.notifier = notifier

    async def run(
        self,
        urls: list[str],
        *,
        concurrency: int = 2,
        headless: bool = True,
    ) -> list[Alert]:
        await self._ingest(urls, concurrency, headless)
        await self._enrich()
        snapshots = await self._load_snapshots()
        alerts = self.alert_engine.evaluate_all(snapshots)
        await self._notify(alerts)
        return alerts

    async def _notify(self, alerts: list[Alert]) -> None:
        if self.notifier is None or not alerts:
            return
        for alert in alerts:
            try:
                await self.notifier.send_alert(alert)
                print(f"  [OK] alerta enviada a Telegram: {alert.property_id}")
            except Exception as exc:  # un fallo de red no aborta el pipeline
                print(f"  [ERROR] telegram: {exc}")

    # -- 1. Ingestión (scrape + guardado) ------------------------------------
    async def _ingest(self, urls, concurrency, headless) -> None:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            sem = asyncio.Semaphore(concurrency)

            async def one(url: str) -> None:
                async with sem:
                    page = await browser.new_page()
                    try:
                        await self.ingestor.ingest_url(page, url)
                        print(f"  [OK] ingerida: {url}")
                    except Exception as exc:  # un fallo no aborta el lote
                        print(f"  [ERROR] {url}: {exc}")
                    finally:
                        await page.close()

            await asyncio.gather(*(one(u) for u in urls))
            await browser.close()

    # -- 2. Enriquecimiento (geolocalización catastral, best-effort) ----------
    async def _enrich(self) -> None:
        resp = await self.client.table("properties").select(
            "id,referencia_catastral,location"
        ).execute()
        targets = [
            row
            for row in (resp.data or [])
            if row.get("referencia_catastral") and not row.get("location")
        ]
        for row in targets:
            try:
                await self.enrichment.geolocate_property(
                    row["id"], row["referencia_catastral"]
                )
                print(f"  [OK] geolocalizada: {row['id']}")
            except Exception as exc:
                print(f"  [ERROR] geolocalización {row['id']}: {exc}")

    # -- 3. Snapshots desde la BD --------------------------------------------
    async def _load_snapshots(self) -> list[PropertySnapshot]:
        resp = await self.client.table("properties").select(
            "id,listings(source,source_id,price,first_seen,status,price_history(price,observed_at))"
        ).execute()
        return [self._to_snapshot(row) for row in (resp.data or [])]

    @staticmethod
    def _to_snapshot(row: dict) -> PropertySnapshot:
        listings = [
            ListingSnapshot(
                source_id=l["source_id"],
                source=l["source"],
                price=Decimal(str(l["price"])),
                first_seen=_parse_dt(l["first_seen"]),
                status=l.get("status") or "active",
                price_history=[
                    PricePoint(
                        price=Decimal(str(h["price"])),
                        observed_at=_parse_dt(h["observed_at"]),
                    )
                    for h in (l.get("price_history") or [])
                ],
            )
            for l in (row.get("listings") or [])
        ]
        return PropertySnapshot(property_id=row["id"], listings=listings)


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline de ingesta + enriquecimiento + alertas."
    )
    parser.add_argument("--url", help="procesar una única URL")
    parser.add_argument("--urls", default="urls.txt", help="archivo con URLs (una por línea)")
    parser.add_argument("--concurrency", type=int, default=2, help="páginas en paralelo")
    parser.add_argument("--headed", action="store_true", help="navegador visible (debug)")
    return parser.parse_args(argv)


async def main(argv=None) -> int:
    args = _parse_args(argv)
    load_dotenv()

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        print("error: faltan SUPABASE_URL y/o SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 1

    urls = _read_urls(args)
    if not urls:
        print("error: no hay URLs que procesar (usa --url o edita urls.txt)", file=sys.stderr)
        return 1

    client = await create_async_client(supabase_url, supabase_key)
    enrichment = EnrichmentService(client)

    notifier = None
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if telegram_token and telegram_chat_id:
        notifier = TelegramNotifier(telegram_token, telegram_chat_id)

    pipeline = Pipeline(
        ingestor=PipelineIngestor(SupabaseListingRepository(client)),
        enrichment=enrichment,
        alert_engine=AlertEngine(),
        client=client,
        notifier=notifier,
    )

    try:
        alerts = await pipeline.run(
            urls, concurrency=args.concurrency, headless=not args.headed
        )
    finally:
        await enrichment.aclose()
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            await aclose()

    if alerts:
        print("\n=== ALERTAS ===")
        for a in alerts:
            print(f"[{a.type}] {a.property_id}: {a.message}")
    else:
        print("\nSin alertas detectadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
