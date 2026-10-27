"""Supabase-backed implementation of the ListingRepository protocol (Phase 3.2).

Idempotent persistence: safe to call repeatedly for the same source/source_id.
Asymmetric payloads: registral fields route to properties, None fields are omitted.
Deterministic dedup: registral identifiers link a new listing to an existing property.
Fuzzy dedup: physical features (bedrooms/bathrooms + ±5% area) match listings lacking registral data.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from supabase import AsyncClient

from buscapisos.models import Listing


class RepositoryError(Exception):
    """Raised when persisting a listing to Supabase fails."""


class SupabaseListingRepository:
    """Persists a Listing into Supabase using the Phase 1 schema.

    Routing in `add()`:

      * New listing      -> INSERT properties, INSERT listings, INSERT price_history.
      * Existing listing -> UPDATE listings; INSERT price_history only if the
                            price changed (the Phase 1 trigger then refreshes
                            last_seen automatically).
    """

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def add(self, listing: Listing) -> None:
        try:
            existing = await self._find_listing(listing)
            if existing is None:
                await self._create(listing)
            else:
                await self._refresh(existing, listing)
        except RepositoryError:
            raise
        except Exception as exc:  # network / API failures from supabase-py
            raise RepositoryError(
                f"failed to persist listing {listing.source_id!r}: {exc}"
            ) from exc

    # -- lookup ---------------------------------------------------------------
    async def _find_listing(self, listing: Listing) -> dict | None:
        response = await (
            self._client.table("listings")
            .select("*")
            .eq("source", listing.source)
            .eq("source_id", listing.source_id)
            .execute()
        )
        rows = self._rows(response, "listings")
        return rows[0] if rows else None

    # -- dedup: match by registral identifiers ---------------------------------
    async def _find_property_by_registral_data(self, listing: Listing) -> str | None:
        cru = listing.cru
        referencia = listing.referencia_catastral
        if cru is None and referencia is None:
            return None  # no registral data -> skip the network round-trip

        query = self._client.table("properties").select("id")
        if cru is not None and referencia is not None:
            response = await query.or_(
                f"cru.eq.{cru},referencia_catastral.eq.{referencia}"
            ).execute()
        elif cru is not None:
            response = await query.eq("cru", cru).execute()
        else:
            response = await query.eq("referencia_catastral", referencia).execute()

        rows = self._rows(response, "properties")
        return self._require_id(rows[0]) if rows else None

    # -- dedup: match by physical features (±5% area) --------------------------
    async def _find_property_by_fuzzy_match(self, listing: Listing) -> str | None:
        area = listing.area
        bedrooms = listing.bedrooms
        bathrooms = listing.bathrooms
        if area is None or bedrooms is None or bathrooms is None:
            return None  # insufficient data -> skip the network round-trip

        low = area * Decimal("0.95")
        high = area * Decimal("1.05")

        response = await (
            self._client.table("properties")
            .select("id")
            .eq("bedrooms", bedrooms)
            .eq("bathrooms", bathrooms)
            .gte("area", str(low))
            .lte("area", str(high))
            .execute()
        )
        rows = self._rows(response, "properties")
        return self._require_id(rows[0]) if rows else None

    # -- new listing ----------------------------------------------------------
    async def _create(self, listing: Listing) -> None:
        property_id = await self._find_property_by_registral_data(listing)
        if property_id is None:
            property_id = await self._find_property_by_fuzzy_match(listing)
        if property_id is None:
            property_id = await self._insert_property(listing)
        listing_id = await self._insert_listing(listing, property_id)
        await self._insert_price_history(listing_id, listing.price)

    # -- existing listing -----------------------------------------------------
    async def _refresh(self, existing: dict, listing: Listing) -> None:
        await self._update_listing(existing, listing)
        if self._prices_differ(existing.get("price"), listing.price):
            await self._insert_price_history(existing["id"], listing.price)

    # -- payload builders -----------------------------------------------------
    @staticmethod
    def _property_payload(listing: Listing) -> dict:
        payload = {
            "property_type": "other",
            "title": listing.title,
        }
        if listing.cru is not None:
            payload["cru"] = listing.cru
        if listing.referencia_catastral is not None:
            payload["referencia_catastral"] = listing.referencia_catastral
        if listing.area is not None:
            payload["area"] = str(listing.area)
        if listing.bedrooms is not None:
            payload["bedrooms"] = listing.bedrooms
        if listing.bathrooms is not None:
            payload["bathrooms"] = listing.bathrooms
        return payload

    @staticmethod
    def _listing_data_payload(listing: Listing) -> dict:
        payload = {
            "url": listing.url,
            "title": listing.title,
            "price": str(listing.price),
        }
        if listing.area is not None:
            payload["area"] = str(listing.area)
        if listing.bedrooms is not None:
            payload["bedrooms"] = listing.bedrooms
        if listing.bathrooms is not None:
            payload["bathrooms"] = listing.bathrooms
        return payload

    # -- individual writes ----------------------------------------------------
    async def _insert_property(self, listing: Listing) -> str:
        payload = self._property_payload(listing)
        response = await self._client.table("properties").insert(payload).execute()
        rows = self._rows(response, "properties")
        return self._require_id(self._require_row(rows, "properties"))

    async def _insert_listing(self, listing: Listing, property_id: str) -> str:
        payload = self._listing_data_payload(listing)
        payload.update({
            "property_id": property_id,
            "source": listing.source,
            "source_id": listing.source_id,
        })
        response = await self._client.table("listings").insert(payload).execute()
        rows = self._rows(response, "listings")
        return self._require_id(self._require_row(rows, "listings"))

    async def _update_listing(self, existing: dict, listing: Listing) -> None:
        # Identity columns (source, source_id, property_id) are never updated.
        payload = self._listing_data_payload(listing)
        await (
            self._client.table("listings")
            .update(payload)
            .eq("id", existing["id"])
            .execute()
        )

    async def _insert_price_history(self, listing_id: str, price: Decimal) -> None:
        payload = {
            "listing_id": listing_id,
            "price": str(price),
        }
        await self._client.table("price_history").insert(payload).execute()

    # -- response/type helpers ------------------------------------------------
    @staticmethod
    def _rows(response: Any, table: str) -> list[dict]:
        # supabase-py v2 returns an APIResponse exposing .data and .error.
        error = getattr(response, "error", None)
        data = getattr(response, "data", None)
        if error:
            raise RepositoryError(f"Supabase error on {table}: {error}")
        return data or []

    @staticmethod
    def _require_row(rows: list[dict], table: str) -> dict:
        if not rows:
            raise RepositoryError(f"Supabase returned no rows for {table}")
        return rows[0]

    @staticmethod
    def _require_id(row: dict) -> str:
        value = row.get("id")
        if not value:
            raise RepositoryError("Supabase did not return an id")
        return str(value)

    @staticmethod
    def _prices_differ(previous: Any, current: Decimal) -> bool:
        try:
            return Decimal(str(previous)) != current
        except (InvalidOperation, TypeError, ValueError):
            return True  # unparseable previous price -> treat as a change
