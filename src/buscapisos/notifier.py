"""Telegram notifier (Phase 2)."""

from __future__ import annotations

import httpx

from buscapisos.alert_engine import Alert

_TELEGRAM_API = "https://api.telegram.org"


class TelegramNotifier:
    """Envía alertas formateadas a un chat de Telegram mediante la Bot API."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._endpoint = f"{_TELEGRAM_API}/bot{bot_token}/sendMessage"
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        async with httpx.AsyncClient() as http:
            response = await http.post(
                self._endpoint,
                json={"chat_id": self._chat_id, "text": text},
            )
            response.raise_for_status()

    async def send_alert(self, alert: Alert) -> None:
        await self.send(self.format_alert(alert))

    @staticmethod
    def format_alert(alert: Alert) -> str:
        if alert.type == "CAPITULATION":
            title = "🔻 CAPITULACIÓN (vendedor motivado)"
        else:
            title = "⚖️ ARBITRAJE INTER-AGENCIA"
        return f"{title}\n🏠 {alert.property_id}\n{alert.message}"
