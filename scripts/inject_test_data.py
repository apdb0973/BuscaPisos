#!/usr/bin/env python3
"""
Inyecta 3 propiedades de prueba en Gran Canaria (Supabase) con sus listings y
price_history, para probar el mapa web sin depender del scraper.

EJECUCIÓN (desde la raíz del proyecto):
    python scripts/inject_test_data.py              # limpia e inserta (por defecto)
    python scripts/inject_test_data.py --reset      # solo borra los datos de prueba
    python scripts/inject_test_data.py --no-reset   # inserta sin limpiar antes

VARIABLES DE ENTORNO (o archivo .env en la raíz del proyecto):
    SUPABASE_URL               -> Project URL (Project Settings > API)
    SUPABASE_SERVICE_ROLE_KEY  -> clave service_role (maestra, backend; NUNCA en frontend)

NOTA: la geometría `location` se envía como GeoJSON
{"type": "Point", "coordinates": [lon, lat]} y PostgREST la convierte a
geometry(Point, 4326) vía PostGIS; Leaflet la lee desde location.coordinates.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv
from supabase import create_async_client

TEST_TITLE_PREFIX = "[TEST] "

# ---------------------------------------------------------------------------
# Datos de prueba: 3 inmuebles en Gran Canaria
# ---------------------------------------------------------------------------
PROPERTIES = [
    {
        "property_type": "apartment",
        "title": "Piso en Triana, Las Palmas de Gran Canaria",
        "location": {"type": "Point", "coordinates": [-15.4153, 28.1035]},
        "area": "92",
        "bedrooms": 3,
        "bathrooms": 2,
        "city": "Las Palmas de Gran Canaria",
        "province": "Las Palmas",
        "is_public": True,
        "listings": [
            {
                "source": "inmovilla",
                "source_id": "TEST-LPA-001",
                "url": "https://demo.inmovilla.com/ficha/TEST-LPA-001",
                "title": "Piso en Triana",
                "price": "289000",
                "area": "92",
                "bedrooms": 3,
                "bathrooms": 2,
                "price_history": [
                    {"price": "320000", "observed_at": "2025-12-01T10:00:00Z"},
                    {"price": "289000", "observed_at": "2026-02-15T10:00:00Z"},
                ],
            }
        ],
    },
    {
        "property_type": "house",
        "title": "Casa en Telde, Gran Canaria",
        "location": {"type": "Point", "coordinates": [-15.4184, 27.9920]},
        "area": "140",
        "bedrooms": 4,
        "bathrooms": 2,
        "city": "Telde",
        "province": "Las Palmas",
        "is_public": True,
        "listings": [
            {
                "source": "inmovilla",
                "source_id": "TEST-TEL-001",
                "url": "https://demo.inmovilla.com/ficha/TEST-TEL-001",
                "title": "Casa en Telde (BOICAN)",
                "price": "150000",
                "area": "140",
                "bedrooms": 4,
                "bathrooms": 2,
                "price_history": [{"price": "150000", "observed_at": "2026-01-10T10:00:00Z"}],
            },
            {
                "source": "other",
                "source_id": "TEST-TEL-002",
                "url": "https://demo.example.com/TEST-TEL-002",
                "title": "Casa en Telde (finn.no)",
                "price": "140000",
                "area": "140",
                "bedrooms": 4,
                "bathrooms": 2,
                "price_history": [{"price": "140000", "observed_at": "2026-01-12T10:00:00Z"}],
            },
        ],
    },
    {
        "property_type": "apartment",
        "title": "Subasta: apartamento en Maspalomas",
        "location": {"type": "Point", "coordinates": [-15.5843, 27.7604]},
        "area": None,
        "bedrooms": None,
        "bathrooms": None,
        "city": "San Bartolomé de Tirajana",
        "province": "Las Palmas",
        "is_public": True,
        "cru": "TEST-CRU-0001",
        "referencia_catastral": "TEST-REF-0001",
        "listings": [
            {
                "source": "boe",
                "source_id": "TEST-BOE-001",
                "url": "https://subastas.boe.es/detalleSubasta?idSub=TEST-BOE-001",
                "title": "Subasta apartamento Maspalomas",
                "price": "75000",
                "area": None,
                "bedrooms": None,
                "bathrooms": None,
                "price_history": [{"price": "75000", "observed_at": "2026-02-01T10:00:00Z"}],
            }
        ],
    },
]


def _clean(payload: dict) -> dict:
    """Elimina las claves con valor None para no enviarlas a PostgREST."""
    return {k: v for k, v in payload.items() if v is not None}


def _require_id(response, table: str) -> str:
    rows = getattr(response, "data", None) or []
    if not rows:
        raise RuntimeError(f"Supabase no devolvió fila al insertar en {table!r}")
    return str(rows[0]["id"])


async def _reset(client) -> None:
    """Borra las propiedades de prueba previas (y en cascada su historial)."""
    resp = await client.table("properties").select("id,title").execute()
    ids = [
        row["id"]
        for row in (getattr(resp, "data", None) or [])
        if (row.get("title") or "").startswith(TEST_TITLE_PREFIX)
    ]
    if not ids:
        print("No hay datos de prueba previos que borrar.")
        return
    # listings -> properties es ON DELETE RESTRICT: borramos primero los listings
    # (price_history cae en cascada) y después las properties.
    await client.table("listings").delete().in_("property_id", ids).execute()
    await client.table("properties").delete().in_("id", ids).execute()
    print(f"Borradas {len(ids)} propiedades de prueba (y sus listings/historial).")


async def _insert_property(client, prop: dict) -> str:
    payload = _clean(
        {
            "property_type": prop["property_type"],
            "title": TEST_TITLE_PREFIX + prop["title"],
            "location": prop["location"],
            "area": prop.get("area"),
            "bedrooms": prop.get("bedrooms"),
            "bathrooms": prop.get("bathrooms"),
            "city": prop.get("city"),
            "province": prop.get("province"),
            "is_public": prop.get("is_public", True),
            "cru": prop.get("cru"),
            "referencia_catastral": prop.get("referencia_catastral"),
        }
    )
    resp = await client.table("properties").insert(payload).execute()
    return _require_id(resp, "properties")


async def _insert_listing(client, property_id: str, listing: dict) -> str:
    payload = _clean(
        {
            "property_id": property_id,
            "source": listing["source"],
            "source_id": listing["source_id"],
            "url": listing.get("url"),
            "title": listing.get("title"),
            "price": listing["price"],
            "area": listing.get("area"),
            "bedrooms": listing.get("bedrooms"),
            "bathrooms": listing.get("bathrooms"),
        }
    )
    resp = await client.table("listings").insert(payload).execute()
    return _require_id(resp, "listings")


async def _insert_price_history(client, listing_id: str, ph: dict) -> None:
    payload = _clean(
        {
            "listing_id": listing_id,
            "price": ph["price"],
            "observed_at": ph.get("observed_at"),
        }
    )
    await client.table("price_history").insert(payload).execute()


async def _insert_all(client) -> None:
    for prop in PROPERTIES:
        property_id = await _insert_property(client, prop)
        for listing in prop["listings"]:
            listing_id = await _insert_listing(client, property_id, listing)
            for ph in listing.get("price_history", []):
                await _insert_price_history(client, listing_id, ph)
        print(f"  -> insertada: {prop['title']}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inyecta 3 propiedades de prueba en Gran Canaria en Supabase."
    )
    parser.add_argument(
        "--reset", action="store_true", help="Solo borra los datos de prueba y sale."
    )
    parser.add_argument(
        "--no-reset", action="store_true", help="Inserta sin limpiar los datos previos."
    )
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    load_dotenv()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print(
            "Error: faltan las variables de entorno SUPABASE_URL y/o "
            "SUPABASE_SERVICE_ROLE_KEY.\n"
            "Cópialas desde Project Settings > API de Supabase, o crea un .env.",
            file=sys.stderr,
        )
        return 1

    client = await create_async_client(url, key)
    try:
        if args.reset:
            await _reset(client)
            return 0
        if not args.no_reset:
            await _reset(client)
        await _insert_all(client)
        print("Datos de prueba inyectados correctamente.")
        return 0
    finally:
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            await aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
