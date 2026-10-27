"""pytest suite for AlertEngine (Phase 5)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from buscapisos.alert_engine import (
    AlertEngine,
    ListingSnapshot,
    PricePoint,
    PropertySnapshot,
)

NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _listing(source_id, source, price, first_seen, history, status="active"):
    return ListingSnapshot(
        source_id=source_id,
        source=source,
        price=Decimal(price),
        first_seen=first_seen,
        price_history=[
            PricePoint(price=Decimal(p), observed_at=o) for p, o in history
        ],
        status=status,
    )


# ---------------------------------------------------------------------------
# 1. Capitulation (motivated seller)
# ---------------------------------------------------------------------------
def test_capitulation_signal_when_old_and_dropped_10_percent():
    # 95 days on market, price 100000 -> 89000 (11% drop).
    listing = _listing(
        "INV-1", "inmovilla", "89000",
        NOW - timedelta(days=95),
        [
            ("100000", NOW - timedelta(days=95)),
            ("89000", NOW - timedelta(days=1)),
        ],
    )
    prop = PropertySnapshot(property_id="prop-1", listings=[listing])

    alerts = AlertEngine(now=NOW).evaluate(prop)

    capitulation = [a for a in alerts if a.type == "CAPITULATION"]
    assert len(capitulation) == 1
    assert capitulation[0].property_id == "prop-1"
    assert capitulation[0].message


def test_no_capitulation_when_recent_even_with_big_drop():
    # 15% drop but only 30 days on market.
    listing = _listing(
        "INV-1", "inmovilla", "85000",
        NOW - timedelta(days=30),
        [
            ("100000", NOW - timedelta(days=30)),
            ("85000", NOW - timedelta(days=1)),
        ],
    )
    prop = PropertySnapshot(property_id="prop-1", listings=[listing])

    alerts = AlertEngine(now=NOW).evaluate(prop)

    assert not [a for a in alerts if a.type == "CAPITULATION"]


def test_no_capitulation_when_small_drop_even_if_old():
    # 100 days on market but only 5% drop.
    listing = _listing(
        "INV-1", "inmovilla", "95000",
        NOW - timedelta(days=100),
        [
            ("100000", NOW - timedelta(days=100)),
            ("95000", NOW - timedelta(days=1)),
        ],
    )
    prop = PropertySnapshot(property_id="prop-1", listings=[listing])

    alerts = AlertEngine(now=NOW).evaluate(prop)

    assert not [a for a in alerts if a.type == "CAPITULATION"]


# ---------------------------------------------------------------------------
# 2. Inter-agency arbitrage
# ---------------------------------------------------------------------------
def test_arbitrage_signal_between_listings():
    listings = [
        _listing(
            "BOICAN-1", "inmovilla", "150000",
            NOW - timedelta(days=10),
            [("150000", NOW - timedelta(days=10))],
        ),
        _listing(
            "FINN-1", "other", "140000",
            NOW - timedelta(days=10),
            [("140000", NOW - timedelta(days=10))],
        ),
    ]
    prop = PropertySnapshot(property_id="prop-1", listings=listings)

    alerts = AlertEngine(now=NOW).evaluate(prop)

    arbitrage = [a for a in alerts if a.type == "ARBITRAGE"]
    assert len(arbitrage) == 1
    assert arbitrage[0].property_id == "prop-1"
    assert "10000" in arbitrage[0].message


def test_no_arbitrage_when_single_listing():
    listing = _listing(
        "INV-1", "inmovilla", "150000",
        NOW - timedelta(days=10),
        [("150000", NOW - timedelta(days=10))],
    )
    prop = PropertySnapshot(property_id="prop-1", listings=[listing])

    alerts = AlertEngine(now=NOW).evaluate(prop)

    assert not [a for a in alerts if a.type == "ARBITRAGE"]
