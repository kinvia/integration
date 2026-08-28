"""Queued webhook client for Kinvia incident reporting."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import SERVER_HEALTH_PATH, WEBHOOK_HEALTH_PATH, WEBHOOK_PATH
from .incident import IncidentPayload

_LOGGER = logging.getLogger(__name__)

_DEFAULT_HEADERS = {"ngrok-skip-browser-warning": "true"}
_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15)


class KinviaWebhookClient:
    """Send incident payloads to Kinvia sequentially (queued mode)."""

    def __init__(
        self,
        base_url: str,
        webhook_secret: str,
        *,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._webhook_secret = webhook_secret
        self._session = session
        self._owns_session = session is None
        self._queue: asyncio.Queue[IncidentPayload | None] | None = None
        self._worker: asyncio.Task[None] | None = None

    @property
    def webhook_url(self) -> str:
        return f"{self._base_url}{WEBHOOK_PATH}"

    async def async_start(self) -> None:
        if self._worker is not None:
            return
        if self._session is None:
            self._session = aiohttp.ClientSession()
        self._queue = asyncio.Queue()
        self._worker = asyncio.create_task(self._process_queue())

    async def async_stop(self) -> None:
        if self._queue is not None:
            await self._queue.put(None)
        if self._worker is not None:
            await self._worker
            self._worker = None
        self._queue = None
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def async_enqueue(self, payload: IncidentPayload) -> None:
        if self._queue is None:
            raise RuntimeError("Kinvia webhook client is not started")
        await self._queue.put(payload)

    async def _process_queue(self) -> None:
        assert self._queue is not None
        while True:
            payload = await self._queue.get()
            if payload is None:
                break
            try:
                status, body = await self._post_payload(payload)
                if status >= 400:
                    _LOGGER.warning(
                        "Kinvia webhook failed (%s): %s — entity=%s type=%s",
                        status,
                        body,
                        payload.entity_id,
                        payload.incident_type,
                    )
            except aiohttp.ClientError as err:
                _LOGGER.warning(
                    "Kinvia webhook connection error for %s: %s",
                    payload.entity_id,
                    err,
                )
            finally:
                self._queue.task_done()

    async def _post_payload(self, payload: IncidentPayload) -> tuple[int, str]:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._webhook_secret,
            **_DEFAULT_HEADERS,
        }
        assert self._session is not None
        async with self._session.post(
            self.webhook_url,
            json=payload.as_dict(),
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            return response.status, await response.text()


async def validate_connection(
    base_url: str,
    webhook_secret: str,
    *,
    session: aiohttp.ClientSession,
) -> dict[str, Any]:
    """Verify Kinvia is reachable and the webhook secret is valid (no side effects)."""
    origin = base_url.rstrip("/")

    async with session.get(
        f"{origin}{SERVER_HEALTH_PATH}",
        headers=_DEFAULT_HEADERS,
        timeout=_DEFAULT_TIMEOUT,
    ) as server_response:
        if server_response.status >= 400:
            return {"status": server_response.status, "step": "server"}

    async with session.get(
        f"{origin}{WEBHOOK_HEALTH_PATH}",
        headers={"x-api-key": webhook_secret, **_DEFAULT_HEADERS},
        timeout=_DEFAULT_TIMEOUT,
    ) as webhook_response:
        return {
            "status": webhook_response.status,
            "body": await webhook_response.text(),
            "step": "webhook",
        }
