"""WebSocket client for Set Play relay (Cloudflare Durable Object)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWebSockets import QWebSocket


class SetPlayRelayClient(QObject):
    """
    Outbound WebSocket to relay. Leader sends JSON text; assistant receives snapshots.
    URL shape: wss://<host>/api/rooms/<code>/ws?leaderToken=<token> (leader) or same without token.
    """

    connected_ok = Signal()
    disconnected = Signal()
    state_received = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ws = QWebSocket()
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self._on_text)
        self._ws.errorOccurred.connect(self._on_error)

    def _on_connected(self) -> None:
        self.connected_ok.emit()

    def _on_disconnected(self) -> None:
        self.disconnected.emit()

    def _on_text(self, msg: str) -> None:
        try:
            data = json.loads(msg)
        except json.JSONDecodeError:
            self.error_occurred.emit("Invalid JSON from relay")
            return
        if isinstance(data, dict):
            self.state_received.emit(data)

    def _on_error(self, _err) -> None:
        self.error_occurred.emit(self._ws.errorString())

    def open_assistant(self, base_url: str, room_code: str) -> None:
        """base_url example: wss://set-play-relay.example.workers.dev (no trailing slash)."""
        url = _join_ws_url(base_url, room_code, leader_token=None)
        self._ws.open(QUrl(url))

    def open_leader(self, base_url: str, room_code: str, leader_token: str) -> None:
        url = _join_ws_url(base_url, room_code, leader_token=leader_token)
        self._ws.open(QUrl(url))

    def send_snapshot(self, payload: dict[str, Any]) -> None:
        if self._ws.state() == QAbstractSocket.SocketState.ConnectedState:
            self._ws.sendTextMessage(json.dumps(payload))

    def close(self) -> None:
        self._ws.close()

    def is_open(self) -> bool:
        return self._ws.state() == QAbstractSocket.SocketState.ConnectedState


def _join_ws_url(base_url: str, room_code: str, leader_token: str | None) -> str:
    b = base_url.rstrip("/")
    code = quote(room_code.strip().upper(), safe="")
    path = f"{b}/api/rooms/{code}/ws"
    if leader_token:
        t = quote(leader_token, safe="")
        return f"{path}?leaderToken={t}"
    return path
