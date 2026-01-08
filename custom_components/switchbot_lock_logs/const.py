"""Constants for the SwitchBot Lock Logs integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "switchbot_lock_logs"
LOGGER = logging.getLogger(__package__)

# Core SwitchBot integration domain
SWITCHBOT_DOMAIN: Final = "switchbot"

# Config entry data keys
CONF_DEVICE_ID: Final = "device_id"
CONF_DEVICE_NAME: Final = "device_name"
CONF_MAC_ADDRESS: Final = "mac_address"

# Lock Log Defaults
DEFAULT_LOCK_LOG_MAX_ENTRIES: Final = 20

# Services
SERVICE_GET_LOCK_LOGS: Final = "get_lock_logs"
SERVICE_SET_LOCK_USER_NAME: Final = "set_lock_user_name"
SERVICE_DELETE_LOCK_USER_NAME: Final = "delete_lock_user_name"

# Storage
STORAGE_KEY_LOCK_USERS: Final = "switchbot_lock_logs_users"
STORAGE_VERSION_LOCK_USERS: Final = 1

# Lock model types (from core switchbot const.py)
LOCK_MODELS: Final = {"lock", "lock_pro", "lock_lite", "lock_ultra"}
