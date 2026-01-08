"""Storage for SwitchBot lock user name mappings."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_LOCK_USERS, STORAGE_VERSION_LOCK_USERS


class SwitchBotLockUserStore:
    """Store lock user name mappings."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self._hass = hass
        self._store: Store[dict] = Store(
            hass, STORAGE_VERSION_LOCK_USERS, STORAGE_KEY_LOCK_USERS
        )
        self._data: dict[str, dict] = {}

    async def async_load(self) -> None:
        """Load data from storage."""
        if data := await self._store.async_load():
            self._data = data
        else:
            self._data = {}

    async def async_save(self) -> None:
        """Save data to storage."""
        await self._store.async_save(self._data)

    async def async_get_lock_data(self, mac: str) -> dict:
        """Get all data for a lock."""
        return self._data.get(mac, {"name": None, "users": {}})

    async def async_get_users(self, mac: str) -> dict[str, str]:
        """Get user mappings for a lock."""
        lock_data = await self.async_get_lock_data(mac)
        return lock_data.get("users", {})

    async def async_set_user(self, mac: str, user_id: int, name: str) -> None:
        """Set a user name mapping."""
        if mac not in self._data:
            self._data[mac] = {"name": None, "users": {}}
        self._data[mac]["users"][str(user_id)] = name
        await self.async_save()

    async def async_delete_user(self, mac: str, user_id: int) -> None:
        """Delete a user name mapping."""
        if mac in self._data and "users" in self._data[mac]:
            self._data[mac]["users"].pop(str(user_id), None)
            await self.async_save()

    async def async_set_lock_name(self, mac: str, name: str) -> None:
        """Set lock friendly name."""
        if mac not in self._data:
            self._data[mac] = {"name": name, "users": {}}
        else:
            self._data[mac]["name"] = name
        await self.async_save()

    async def async_get_lock_name(self, mac: str) -> str | None:
        """Get lock friendly name."""
        lock_data = await self.async_get_lock_data(mac)
        return lock_data.get("name")
