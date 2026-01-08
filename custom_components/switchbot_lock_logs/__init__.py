"""SwitchBot Lock Logs - Companion integration for lock operation history."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_DEVICE_ID,
    CONF_MAC_ADDRESS,
    DEFAULT_LOCK_LOG_MAX_ENTRIES,
    DOMAIN,
    LOGGER,
    SERVICE_DELETE_LOCK_USER_NAME,
    SERVICE_GET_LOCK_LOGS,
    SERVICE_SET_LOCK_USER_NAME,
    SWITCHBOT_DOMAIN,
)
from .lock_log_manager import SwitchBotLockLogManager
from .storage import SwitchBotLockUserStore

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.helpers.event import EventStateChangedData
    from switchbot import SwitchbotLock

# Delay before fetching logs after state change (seconds)
# This gives the lock firmware time to write the log entry
LOG_FETCH_DELAY = 2.0

# Minimum time between log fetches (seconds) - debouncing
LOG_FETCH_DEBOUNCE = 3.0

# Integration can only be configured via config entries
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class SwitchBotLockLogsData:
    """Runtime data for a SwitchBot Lock Logs config entry."""

    log_manager: SwitchBotLockLogManager
    mac_address: str
    cancel_state_listener: Callable[[], None] | None = None
    _pending_fetch_task: asyncio.Task | None = field(default=None, repr=False)


type SwitchBotLockLogsConfigEntry = ConfigEntry[SwitchBotLockLogsData]


async def async_setup(
    hass: HomeAssistant,
    config: dict,  # noqa: ARG001
) -> bool:
    """Set up the SwitchBot Lock Logs component."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize user store (shared across all locks)
    if "user_store" not in hass.data[DOMAIN]:
        user_store = SwitchBotLockUserStore(hass)
        await user_store.async_load()
        hass.data[DOMAIN]["user_store"] = user_store

    # Register services
    await _async_register_services(hass)

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchBotLockLogsConfigEntry,
) -> bool:
    """Set up SwitchBot Lock Logs from a config entry."""
    device_id = entry.data[CONF_DEVICE_ID]
    mac_address = entry.data[CONF_MAC_ADDRESS]

    # Ensure user store is initialized
    if "user_store" not in hass.data[DOMAIN]:
        user_store = SwitchBotLockUserStore(hass)
        await user_store.async_load()
        hass.data[DOMAIN]["user_store"] = user_store

    user_store = hass.data[DOMAIN]["user_store"]

    # Find the SwitchBot lock device from the core integration
    lock_device = await _get_switchbot_lock_device(hass, device_id)
    if lock_device is None:
        msg = (
            f"Could not find SwitchBot lock device. Make sure the core SwitchBot "
            f"integration is configured for this lock (device_id: {device_id})"
        )
        raise HomeAssistantError(msg)

    # Create log manager
    log_manager = SwitchBotLockLogManager(
        hass,
        lock_device,
        mac_address,
        user_store,
    )

    # Store runtime data
    entry.runtime_data = SwitchBotLockLogsData(
        log_manager=log_manager,
        mac_address=mac_address,
    )

    # Store log manager for services
    if "log_managers" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["log_managers"] = {}
    hass.data[DOMAIN]["log_managers"][entry.entry_id] = log_manager

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Find the lock entity and subscribe to state changes
    lock_entity_id = await _find_lock_entity_id(hass, device_id)
    if lock_entity_id:
        LOGGER.debug("Subscribing to state changes for %s", lock_entity_id)

        @callback
        def _async_on_lock_state_change(event: Event[EventStateChangedData]) -> None:
            """Handle lock state changes with debouncing."""
            old_state = event.data["old_state"]
            new_state = event.data["new_state"]

            if old_state is None or new_state is None:
                return

            # Only fetch logs if state actually changed
            if old_state.state != new_state.state:
                LOGGER.debug(
                    "Lock state changed from %s to %s, scheduling log fetch",
                    old_state.state,
                    new_state.state,
                )
                # Cancel any pending fetch task (debouncing)
                if entry.runtime_data._pending_fetch_task is not None:
                    entry.runtime_data._pending_fetch_task.cancel()
                    LOGGER.debug("Cancelled pending log fetch (debouncing)")

                # Schedule a new fetch with delay
                entry.runtime_data._pending_fetch_task = hass.async_create_task(
                    _async_delayed_fetch_logs(log_manager, LOG_FETCH_DELAY)
                )

        cancel_listener = async_track_state_change_event(
            hass, [lock_entity_id], _async_on_lock_state_change
        )
        entry.runtime_data.cancel_state_listener = cancel_listener
        entry.async_on_unload(cancel_listener)
    else:
        LOGGER.warning("Could not find lock entity for device %s", device_id)

    # Fetch initial logs (with a small delay to let core integration settle)
    hass.async_create_task(_async_delayed_fetch_logs(log_manager, 1.0))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: SwitchBotLockLogsConfigEntry,
) -> bool:
    """Unload a config entry."""
    # Remove log manager
    hass.data[DOMAIN]["log_managers"].pop(entry.entry_id, None)

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_delayed_fetch_logs(
    log_manager: SwitchBotLockLogManager,
    delay: float,
) -> None:
    """Fetch logs after a delay, with error handling."""
    try:
        await asyncio.sleep(delay)
        LOGGER.debug("Fetching logs after %.1fs delay", delay)
        await log_manager.async_fetch_logs()
    except asyncio.CancelledError:
        LOGGER.debug("Log fetch cancelled (debounced)")
        raise
    except Exception:
        LOGGER.exception("Error fetching logs")


async def _find_lock_entity_id(hass: HomeAssistant, device_id: str) -> str | None:
    """Find the lock entity ID for a device."""
    ent_reg = er.async_get(hass)

    # Find entities for this device that are locks
    for entity in er.async_entries_for_device(ent_reg, device_id):
        if entity.domain == "lock" and entity.platform == SWITCHBOT_DOMAIN:
            return entity.entity_id

    return None


async def _get_switchbot_lock_device(
    hass: HomeAssistant, device_id: str
) -> SwitchbotLock | None:
    """Get the SwitchbotLock device from the core integration."""
    # Import here to avoid circular imports at runtime
    from switchbot import SwitchbotLock  # noqa: PLC0415

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get(device_id)

    if not device:
        LOGGER.error("Device not found: %s", device_id)
        return None

    # Find the switchbot config entry
    switchbot_entry_id = None
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == SWITCHBOT_DOMAIN:
            switchbot_entry_id = entry_id
            break

    if not switchbot_entry_id:
        LOGGER.error("No SwitchBot config entry found for device: %s", device_id)
        return None

    # Get the config entry and extract the lock device
    switchbot_entry = hass.config_entries.async_get_entry(switchbot_entry_id)
    if not switchbot_entry or not hasattr(switchbot_entry, "runtime_data"):
        LOGGER.error(
            "SwitchBot config entry has no runtime data: %s", switchbot_entry_id
        )
        return None

    coordinator = switchbot_entry.runtime_data
    if not coordinator:
        LOGGER.error("No coordinator in runtime data")
        return None

    lock_device = getattr(coordinator, "device", None)
    if lock_device is None or not isinstance(lock_device, SwitchbotLock):
        LOGGER.error("Device is not a SwitchbotLock: %s", type(lock_device))
        return None

    return lock_device


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register lock-related services."""
    if hass.services.has_service(DOMAIN, SERVICE_GET_LOCK_LOGS):
        return

    async def async_get_lock_logs(call: ServiceCall) -> ServiceResponse:
        """Get lock logs service."""
        device_id = call.data["device_id"]
        max_entries = call.data.get("max_entries", DEFAULT_LOCK_LOG_MAX_ENTRIES)
        base_time = call.data.get("base_time", 0)

        # Find log manager for this device
        log_manager = await _find_log_manager_for_device(hass, device_id)
        if not log_manager:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_configured",
            )

        try:
            logs = await log_manager.async_fetch_logs(base_time, max_entries)
        except Exception as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="fetch_logs_error",
            ) from err

        return {"logs": logs}

    async def async_set_lock_user_name(call: ServiceCall) -> None:
        """Set lock user name service."""
        device_id = call.data["device_id"]
        user_id = call.data["user_id"]
        name = call.data["name"]

        log_manager = await _find_log_manager_for_device(hass, device_id)
        if not log_manager:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_configured",
            )

        user_store: SwitchBotLockUserStore = hass.data[DOMAIN]["user_store"]
        await user_store.async_set_user(log_manager.mac, user_id, name)

    async def async_delete_lock_user_name(call: ServiceCall) -> None:
        """Delete lock user name service."""
        device_id = call.data["device_id"]
        user_id = call.data["user_id"]

        log_manager = await _find_log_manager_for_device(hass, device_id)
        if not log_manager:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_configured",
            )

        user_store: SwitchBotLockUserStore = hass.data[DOMAIN]["user_store"]
        await user_store.async_delete_user(log_manager.mac, user_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_LOCK_LOGS,
        async_get_lock_logs,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_LOCK_USER_NAME, async_set_lock_user_name
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_LOCK_USER_NAME, async_delete_lock_user_name
    )


async def _find_log_manager_for_device(
    hass: HomeAssistant, device_id: str
) -> SwitchBotLockLogManager | None:
    """Find the log manager for a given device ID."""
    log_managers: dict[str, SwitchBotLockLogManager] = hass.data[DOMAIN].get(
        "log_managers", {}
    )

    LOGGER.debug(
        "Looking for log manager for device_id: %s, available managers: %d",
        device_id,
        len(log_managers),
    )

    # Look for entry that matches this device
    for entry_id, log_manager in log_managers.items():
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry:
            entry_device_id = entry.data.get(CONF_DEVICE_ID)
            LOGGER.debug(
                "Checking entry %s with device_id: %s (match: %s)",
                entry_id,
                entry_device_id,
                entry_device_id == device_id,
            )
            if entry_device_id == device_id:
                LOGGER.debug("Found matching log manager for device %s", device_id)
                return log_manager

    LOGGER.warning(
        "No log manager found for device_id: %s. Available entries: %s",
        device_id,
        [
            (
                entry_id,
                hass.config_entries.async_get_entry(entry_id).data.get(CONF_DEVICE_ID),
            )
            for entry_id in log_managers.keys()
            if hass.config_entries.async_get_entry(entry_id)
        ],
    )
    return None
