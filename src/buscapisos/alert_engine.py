"""Alert engine: capitulation & inter-agency arbitrage signals (Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Literal

AlertType = Literal["CAPITULATION", "ARBITRAGE"]


@dataclass(frozen=True)
class PricePoint:
    price: Decimal
    observed_at: datetime


@dataclass(frozen=True)
class ListingSnapshot:
    source_id: str
    source: str
    price: Decimal
    first_seen: datetime
    price_history: list[PricePoint] = field(default_factory=list)
    status: str = "active"


@dataclass(frozen=True)
class PropertySnapshot:
    property_id: str
    listings: list[ListingSnapshot]


@dataclass(frozen=True)
class Alert:
    type: AlertType
    property_id: str
    message: str


class AlertEngine:
    """Evaluates properties and their listings to detect investment signals.

    Pure business logic: receives structured snapshots and returns Alert objects,
    without touching the database or the network. The clock is injectable for
    deterministic tests.
    """

    def __init__(
        self,
        *,
        days_on_market_threshold: int = 90,
        price_drop_threshold: Decimal = Decimal("10.0"),
        now: datetime | None = None,
    ) -> None:
        self.days_on_market_threshold = days_on_market_threshold
        self.price_drop_threshold = price_drop_threshold
        self._now = now if now is not None else datetime.now(timezone.utc)

    def evaluate(self, property: PropertySnapshot) -> list[Alert]:
        alerts: list[Alert] = []
        alerts.extend(self._check_capitulation(property))
        alerts.extend(self._check_arbitrage(property))
        return alerts

    def evaluate_all(self, properties: Iterable[PropertySnapshot]) -> list[Alert]:
        alerts: list[Alert] = []
        for property in properties:
            alerts.extend(self.evaluate(property))
        return alerts

    # -- Capitulation (motivated seller) -------------------------------------
    def _check_capitulation(self, property: PropertySnapshot) -> list[Alert]:
        alerts: list[Alert] = []
        for listing in property.listings:
            days_on_market = (self._now - listing.first_seen).days
            if days_on_market <= self.days_on_market_threshold:
                continue

            if not listing.price_history:
                continue

            initial = listing.price_history[0].price
            current = listing.price
            if initial <= 0:
                continue

            drop_pct = (initial - current) / initial * 100
            if drop_pct < self.price_drop_threshold:
                continue

            alerts.append(
                Alert(
                    type="CAPITULATION",
                    property_id=property.property_id,
                    message=(
                        f"Capitulación: {days_on_market} días en el mercado, "
                        f"caída del {drop_pct:.1f}% ({initial} € → {current} €)"
                    ),
                )
            )
        return alerts

    # -- Inter-agency arbitrage ----------------------------------------------
    def _check_arbitrage(self, property: PropertySnapshot) -> list[Alert]:
        active = [l for l in property.listings if l.status == "active"]
        if len(active) < 2:
            return []

        prices = [l.price for l in active]
        min_price = min(prices)
        max_price = max(prices)
        if max_price <= min_price:
            return []

        diff = max_price - min_price
        return [
            Alert(
                type="ARBITRAGE",
                property_id=property.property_id,
                message=(
                    f"Arbitraje inter-agencia: {len(active)} anuncios activos, "
                    f"diferencia de {diff} € (de {min_price} € a {max_price} €)"
                ),
            )
        ]
