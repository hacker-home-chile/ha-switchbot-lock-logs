"""Lock log fetching and enrichment for SwitchBot locks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from switchbot import SwitchbotLock
from switchbot.const import LockLogAction, LockLogSource

from .const import LOGGER
from .storage import SwitchBotLockUserStore


class SwitchBotLockLogManager:
    """Manage lock logs for a single lock device."""

    def __init__(
        self,
        hass: HomeAssistant,
        lock_device: SwitchbotLock,
        mac: str,
        user_store: SwitchBotLockUserStore,
    ) -> None:
        """Initialize the log manager."""
        self._hass = hass
        self._lock_device = lock_device
        self._mac = mac
        self._user_store = user_store
        self._latest_logs: list[dict[str, Any]] = []
        self._listeners: list[Callable[[], None]] = []

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """
        Add a listener to be notified of log updates.

        Returns a function to remove the listener.
        """
        self._listeners.append(listener)

        def remove_listener() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove_listener

    @callback
    def _notify_listeners(self) -> None:
        """Notify all listeners of log update."""
        for listener in self._listeners:
            listener()

    async def async_fetch_logs(
        self, base_time: int = 0, max_entries: int = 10
    ) -> list[dict[str, Any]]:
        """
        Fetch logs from device and enrich with user names.

        Returns all logs without filtering. Filtering for sensor updates
        is handled by the sensor itself.
        """
        # Fetch from BLE device
        LOGGER.debug("Fetching logs for %s", self._mac)
        logs = await self._lock_device.get_logs(base_time, max_entries)

        if not logs:
            LOGGER.debug("No logs retrieved for %s", self._mac)
            return []

        LOGGER.debug("Retrieved %d logs for %s", len(logs), self._mac)

        # Enrich with user names
        enriched_logs = await self._enrich_logs(logs)

        # Store for sensors to read
        self._latest_logs = enriched_logs

        # Notify all sensor entities to update their state
        self._notify_listeners()

        return enriched_logs

    async def _enrich_logs(self, logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Add user names and human-readable fields to logs."""
        users = await self._user_store.async_get_users(self._mac)

        enriched = []
        for log in logs:
            # Extract user ID from payload if present
            user_id = self._extract_user_id(log.get("payload", ""))

            # Determine user name (only for mapped users with IDs)
            if user_id is not None and str(user_id) in users:
                # User ID exists and is mapped to a name
                user_name = users[str(user_id)]
            else:
                # No user ID or not mapped - leave as None for sensor
                user_name = None

            # Determine source name for activity tracking
            try:
                source_name = LockLogSource(log["source"]).name
                source_display = source_name.replace("_", " ").title()
            except (ValueError, KeyError):
                source_display = f"Unknown (Source {log.get('source', '?')})"

            # Add human-readable action
            try:
                action_name = LockLogAction(log["action"]).name.lower()
            except (ValueError, KeyError):
                action_name = f"unknown_{log.get('action', '?')}"

            # Add enriched fields
            enriched_log = {
                **log,
                "user_id": user_id,
                "user_name": user_name,
                "source_display": source_display,
                "action_name": action_name,
            }
            enriched.append(enriched_log)

        return enriched

    @staticmethod
    def _extract_user_id(payload: str) -> int | None:
        """
        Extract user ID from log payload.

        Payload formats:
        - 59 03 XX YY 00 00 (hex string) - Type 3 pattern
        - 59 01 XX YY 00 00 (hex string) - Type 1 pattern
        Where XX (byte 2) is the user ID.
        """
        if not payload or len(payload) < 6:
            return None

        try:
            # Check for pattern 0x59XX (any type)
            if payload[0:2] == "59" and payload[2:4] in ("01", "03"):
                # Extract byte 2 (characters 4-5) - user ID
                user_id = int(payload[4:6], 16)
                # User ID 0 means no user (system action)
                return user_id if user_id > 0 else None
        except (ValueError, IndexError):
            pass

        return None

    @property
    def latest_log(self) -> dict[str, Any] | None:
        """Get the most recent log entry."""
        return self._latest_logs[0] if self._latest_logs else None

    @property
    def latest_logs(self) -> list[dict[str, Any]]:
        """Get all cached logs."""
        return self._latest_logs.copy()

    @property
    def mac(self) -> str:
        """Get the MAC address."""
        return self._mac
