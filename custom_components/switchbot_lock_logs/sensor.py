"""Sensor platform for SwitchBot Lock Logs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, CONF_MAC_ADDRESS, DOMAIN, SWITCHBOT_DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import SwitchBotLockLogsConfigEntry
    from .lock_log_manager import SwitchBotLockLogManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchBotLockLogsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    log_manager = entry.runtime_data.log_manager
    device_id = entry.data[CONF_DEVICE_ID]
    device_name = entry.data[CONF_DEVICE_NAME]
    mac_address = entry.data[CONF_MAC_ADDRESS]

    async_add_entities([
        SwitchBotLockLastActivitySensor(
            log_manager, device_id, device_name, mac_address
        ),
        SwitchBotLockLastUserSensor(
            log_manager, device_id, device_name, mac_address
        ),
    ])


class SwitchBotLockLogSensorBase(SensorEntity):
    """Base class for lock log sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        log_manager: SwitchBotLockLogManager,
        device_id: str,
        device_name: str,
        mac_address: str,
    ) -> None:
        """Initialize the sensor."""
        self._log_manager = log_manager
        self._device_id = device_id
        self._device_name = device_name
        self._mac_address = mac_address

        # Link to the parent SwitchBot device
        self._attr_device_info = DeviceInfo(
            identifiers={(SWITCHBOT_DOMAIN, mac_address)},
        )

    async def async_added_to_hass(self) -> None:
        """Register for log updates."""
        self.async_on_remove(
            self._log_manager.async_add_listener(self._handle_log_update)
        )

    @callback
    def _handle_log_update(self) -> None:
        """Handle log update notification."""
        self.async_write_ha_state()


class SwitchBotLockLastActivitySensor(SwitchBotLockLogSensorBase):
    """Sensor showing last lock activity timestamp."""

    _attr_translation_key = "last_activity"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        log_manager: SwitchBotLockLogManager,
        device_id: str,
        device_name: str,
        mac_address: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(log_manager, device_id, device_name, mac_address)
        self._attr_unique_id = f"{mac_address}-last_activity"
        self._attr_name = "Last activity"

    @property
    def native_value(self) -> datetime | None:
        """Return timestamp of last activity."""
        if latest := self._log_manager.latest_log:
            return datetime.fromtimestamp(latest["timestamp"], tz=timezone.utc)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not (latest := self._log_manager.latest_log):
            return {}

        return {
            "user_name": latest.get("user_name") or "Unknown",
            "action": latest.get("action_name", "unknown"),
            "source": latest.get("source_display", "unknown"),
            "user_id": latest.get("user_id"),
        }


class SwitchBotLockLastUserSensor(SwitchBotLockLogSensorBase):
    """Sensor showing who last used the lock."""

    _attr_translation_key = "last_user"
    _attr_icon = "mdi:account"

    def __init__(
        self,
        log_manager: SwitchBotLockLogManager,
        device_id: str,
        device_name: str,
        mac_address: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(log_manager, device_id, device_name, mac_address)
        self._attr_unique_id = f"{mac_address}-last_user"
        self._attr_name = "Last user"
        self._last_processed_timestamp: int = 0
        self._current_log: dict[str, Any] | None = None

    @callback
    def _handle_log_update(self) -> None:
        """Handle log update notification.

        Filters logs to find the newest entry that:
        - Is newer than the last processed timestamp
        - Has a non-zero payload (indicating a real user action)
        """
        new_log = self._get_newest_valid_log()
        if new_log:
            self._current_log = new_log
            self._last_processed_timestamp = new_log.get("timestamp", 0)
        self.async_write_ha_state()

    def _get_newest_valid_log(self) -> dict[str, Any] | None:
        """Get the newest log that is valid and newer than last processed."""
        for log in self._log_manager.latest_logs:
            timestamp = log.get("timestamp", 0)
            if timestamp > self._last_processed_timestamp and self._is_valid_payload(
                log.get("payload", "")
            ):
                return log
        return None

    @staticmethod
    def _is_valid_payload(payload: str) -> bool:
        """Check if payload is valid (non-zero).

        A valid payload indicates a real user action rather than a system event.
        """
        if not payload or len(payload) < 6:
            return False
        return payload != "000000000000"

    @property
    def native_value(self) -> str | None:
        """Return name of last user (only if mapped, otherwise None)."""
        if self._current_log:
            return self._current_log.get("user_name")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self._current_log:
            return {}

        attributes: dict[str, Any] = {
            "last_activity": self._current_log.get("source_display", "Unknown"),
            "last_activity_timestamp": self._current_log.get("timestamp"),
            "last_activity_action": self._current_log.get("action_name", "unknown"),
            "source": self._current_log.get("source"),
            "payload": self._current_log.get("payload"),
        }

        # Add user_id only if present
        if self._current_log.get("user_id") is not None:
            attributes["user_id"] = self._current_log["user_id"]

        return attributes
