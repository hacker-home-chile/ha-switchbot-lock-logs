# SwitchBot Lock Logs

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that adds lock operation history (logs) to SwitchBot locks. This is a companion integration that works alongside the core SwitchBot integration.

## Features

- **Last Activity Sensor**: Shows the timestamp of the last lock operation
- **Last User Sensor**: Shows who last used the lock (when user names are mapped)
- **User Name Mapping**: Map user IDs to friendly names (e.g., "Dad's Fingerprint", "Guest Code")
- **Service to Fetch Logs**: Manually trigger log fetching from the lock

## Requirements

- Home Assistant 2024.1.0 or newer
- HACS installed
- Core SwitchBot integration configured with your lock
- SwitchBot Lock, Lock Pro, Lock Lite, or Lock Ultra

## Installation

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add `https://github.com/hacker-home-chile/ha-switchbot-lock-logs` as an Integration
5. Click "Add"
6. Search for "SwitchBot Lock Logs" in HACS
7. Click "Download"
8. Restart Home Assistant

### Manual Installation

1. Download the latest release from GitHub
2. Copy the `custom_components/switchbot_lock_logs` folder to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Make sure your SwitchBot lock is already configured in the core SwitchBot integration
2. Go to **Settings** > **Devices & Services** > **Add Integration**
3. Search for "SwitchBot Lock Logs"
4. Select your lock from the dropdown
5. Click "Submit"

## Services

### `switchbot_lock_logs.get_lock_logs`

Fetch lock logs from the device.

| Field | Type | Description |
|-------|------|-------------|
| `device_id` | string | The lock device ID |
| `max_entries` | int | Maximum number of logs to fetch (default: 20) |
| `base_time` | int | Unix timestamp - only get logs after this time (default: 0 = all) |

### `switchbot_lock_logs.set_lock_user_name`

Map a user ID to a friendly name.

| Field | Type | Description |
|-------|------|-------------|
| `device_id` | string | The lock device ID |
| `user_id` | int | User ID from lock logs (0-255) |
| `name` | string | Friendly name for this user |

### `switchbot_lock_logs.delete_lock_user_name`

Remove a user name mapping.

| Field | Type | Description |
|-------|------|-------------|
| `device_id` | string | The lock device ID |
| `user_id` | int | User ID to remove |

## Sensors

| Sensor | Description |
|--------|-------------|
| Last Activity | Timestamp of the last lock operation |
| Last User | Name of the last user (if mapped) |

## Finding User IDs

To find user IDs for mapping:

1. Call the `switchbot_lock_logs.get_lock_logs` service
2. Check the response for the `user_id` field in each log entry
3. Match the user ID with the action (fingerprint unlock, keypad code, etc.)
4. Use `set_lock_user_name` to map the ID to a name

## Dependencies

This integration requires a forked version of pySwitchbot that includes lock log support:
- [hacker-home-chile/pySwitchbot](https://github.com/hacker-home-chile/pySwitchbot)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please open an issue or pull request on GitHub.
