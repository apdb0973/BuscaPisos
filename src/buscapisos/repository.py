"""Repository pattern for persisting (or simulating) extracted listings."""

from __future__ import annotations

from typing import Protocol

from buscapisos.models import Listing


class ListingRepository(Protocol):
    """Interface for listing persistence.

    The DB-backed implementation (Supabase + the Phase 1 schema) will replace
    the in-memory fake in a later iteration; the scraper only depends on this
    protocol, never on a concrete repository.
    """

    async def add(self, listing: Listing) -> None:
        """Persist a single listing."""
        ...


class InMemoryListingRepository:
    """Fake repository that simulates insertion by storing listings in memory."""

    def __init__(self) -> None:
        self._listings: list[Listing] = []

    async def add(self, listing: Listing) -> None:
        self._listings.append(listing)

    def count(self) -> int:
        return len(self._listings)

    def all(self) -> list[Listing]:
        return list(self._listings)
