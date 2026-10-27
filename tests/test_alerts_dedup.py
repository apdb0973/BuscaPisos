"""Tests for alert deduplication (only new alerts are notified once)."""

from buscapisos.alert_engine import Alert
from buscapisos.pipeline import Pipeline


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeClient:
    """Mimics the supabase-py async chain used by Pipeline.

    Supports:
      * client.table('alerts').upsert(payload, ignore_duplicates=True).execute()
      * client.table('alerts').update(payload).eq('dedup_key', key).execute()
    """

    def __init__(self, existing_keys=()):
        self.existing = set(existing_keys)
        self.upserts: list[dict] = []
        self.updates: list[tuple[dict, tuple]] = []

    def table(self, name):
        assert name == "alerts", f"unexpected table {name!r}"
        return self._Builder(self)

    class _Builder:
        def __init__(self, client):
            self._client = client

        def upsert(self, payload, *, ignore_duplicates=False):
            return _FakeClient._Op(self._client, "upsert", payload, ignore_duplicates)

        def update(self, payload):
            return _FakeClient._Op(self._client, "update", payload)

    class _Op:
        def __init__(self, client, kind, payload, ignore_duplicates=False):
            self._client = client
            self._kind = kind
            self._payload = payload
            self._ignore_duplicates = ignore_duplicates
            self._eq = None

        def eq(self, column, value):
            self._eq = (column, value)
            return self

        async def execute(self):
            if self._kind == "upsert":
                key = self._payload["dedup_key"]
                if self._ignore_duplicates and key in self._client.existing:
                    return _FakeResponse([])  # duplicate -> not inserted
                self._client.existing.add(key)
                self._client.upserts.append(self._payload)
                return _FakeResponse([self._payload])  # inserted now
            self._client.updates.append((self._payload, self._eq))
            return _FakeResponse([])


class _RecordingNotifier:
    def __init__(self, fail_for=()):
        self.sent: list[Alert] = []
        self._fail_for = set(fail_for)

    async def send_alert(self, alert):
        if alert.property_id in self._fail_for:
            raise RuntimeError("telegram unavailable")
        self.sent.append(alert)


def _make_pipeline(client, notifier=None):
    return Pipeline(
        ingestor=None,
        enrichment=None,
        alert_engine=None,
        client=client,
        notifier=notifier,
    )


async def test_record_alerts_returns_only_new():
    client = _FakeClient(existing_keys={"ARBITRAGE:prop-2"})
    pipeline = _make_pipeline(client)

    alerts = [
        Alert(type="ARBITRAGE", property_id="prop-1", message="nueva"),
        Alert(type="ARBITRAGE", property_id="prop-2", message="ya vista"),
    ]

    new = await pipeline._record_alerts(alerts)

    assert [a.property_id for a in new] == ["prop-1"]
    assert len(client.upserts) == 1
    assert client.upserts[0]["dedup_key"] == "ARBITRAGE:prop-1"


async def test_notify_marks_notified_only_on_success():
    client = _FakeClient()
    notifier = _RecordingNotifier(fail_for={"prop-bad"})
    pipeline = _make_pipeline(client, notifier)

    alerts = [
        Alert(type="ARBITRAGE", property_id="prop-ok", message="ok"),
        Alert(type="CAPITULATION", property_id="prop-bad", message="falla"),
    ]

    await pipeline._notify(alerts)

    assert [a.property_id for a in notifier.sent] == ["prop-ok"]
    assert len(client.updates) == 1
    assert client.updates[0][1] == ("dedup_key", "ARBITRAGE:prop-ok")


async def test_notify_noop_when_no_notifier():
    client = _FakeClient()
    pipeline = _make_pipeline(client, notifier=None)

    await pipeline._notify([Alert(type="ARBITRAGE", property_id="prop-1", message="x")])

    assert client.updates == []
