"""Config flow for SwitchBot Lock Logs integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import selector

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_MAC_ADDRESS,
    DOMAIN,
    LOCK_MODELS,
    LOGGER,
    SWITCHBOT_DOMAIN,
)


class SwitchBotLockLogsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SwitchBot Lock Logs."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._available_locks: dict[str, dict[str, str]] = {}

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial step - select a lock device."""
        errors: dict[str, str] = {}

        # Find all SwitchBot lock devices
        await self._async_find_switchbot_locks()

        if not self._available_locks:
            return self.async_abort(reason="no_locks_found")

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]

            if device_id not in self._available_locks:
                errors["base"] = "device_not_found"
            else:
                lock_info = self._available_locks[device_id]

                # Check if already configured
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"{lock_info['name']} Logs",
                    data={
                        CONF_DEVICE_ID: device_id,
                        CONF_DEVICE_NAME: lock_info["name"],
                        CONF_MAC_ADDRESS: lock_info["mac"],
                    },
                )

        # Build device selector options
        device_options = [
            selector.SelectOptionDict(
                value=device_id,
                label=f"{info['name']} ({info['mac']})",
            )
            for device_id, info in self._available_locks.items()
        ]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=device_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                }
            ),
            errors=errors,
        )

    async def _async_find_switchbot_locks(self) -> None:
        """Find all SwitchBot lock devices from the core integration."""
        self._available_locks = {}
        dev_reg = dr.async_get(self.hass)

        # Get all devices
        for device in dev_reg.devices.values():
            # Check if device belongs to switchbot integration
            is_switchbot = False
            for entry_id in device.config_entries:
                entry = self.hass.config_entries.async_get_entry(entry_id)
                if entry and entry.domain == SWITCHBOT_DOMAIN:
                    is_switchbot = True
                    # Check if it's a lock based on the sensor_type in entry data
                    sensor_type = entry.data.get("sensor_type", "")
                    if sensor_type in LOCK_MODELS:
                        # Extract MAC from connections
                        mac = None
                        for connection in device.connections:
                            if connection[0] == dr.CONNECTION_BLUETOOTH:
                                mac = connection[1]
                                break

                        if mac:
                            # Check if not already configured for this integration
                            existing_entries = self.hass.config_entries.async_entries(
                                DOMAIN
                            )
                            already_configured = any(
                                e.data.get(CONF_DEVICE_ID) == device.id
                                for e in existing_entries
                            )

                            if not already_configured:
                                self._available_locks[device.id] = {
                                    "name": device.name or "SwitchBot Lock",
                                    "mac": mac,
                                }
                    break

        LOGGER.debug("Found %d available SwitchBot locks", len(self._available_locks))
