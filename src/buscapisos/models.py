"""Pydantic models for extracted listings."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["inmovilla", "idealista", "kyero", "boe", "other"]


class Listing(BaseModel):
    """A validated listing record extracted from a scraped page.

    The scraper parses raw strings (e.g. "320.000 €", "115 m²") into clean
    numeric types *before* constructing this model; Pydantic then enforces the
    final types and the non-empty / positive invariants below.
    """

    title: str = Field(min_length=1, description="Listing title/headline")
    price: Decimal = Field(gt=0, description="Asking price / actionable price in EUR")
    area: Decimal | None = Field(default=None, gt=0, description="Built surface in m²")
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    url: str = Field(min_length=1, description="Canonical URL of the ad")
    source_id: str = Field(min_length=1, description="Internal reference from the source")
    source: Source = "inmovilla"
    source_name: str | None = None  # fuente concreta cuando source == "other"

    # Registral identifiers (Phase 2.4)
    cru: str | None = None
    referencia_catastral: str | None = None

    # Auction-specific (Phase 2.4)
    auction_value: Decimal | None = Field(default=None, gt=0)
    minimum_bid: Decimal | None = Field(default=None, gt=0)
