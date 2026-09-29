# Chaster for Home Assistant

[![Version](https://img.shields.io/github/v/release/jonny5509/Chaster-ha?display_name=tag&sort=semver)](https://github.com/jonny5509/Chaster-ha/releases/latest)
[![HACS](https://img.shields.io/badge/HACS-Custom%20Integration-41BDF5.svg)](https://hacs.xyz/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A Home Assistant custom integration for the **Chaster Public API**.

Chaster brings lock, session, task, countdown, conversation, and supported lock-control information into Home Assistant through a native Config Flow integration.

## ✨ Features

- 🔐 Developer/API token authentication
- 🧩 Home Assistant Config Flow setup
- 👤 Wearer and keyholder support
- 🔒 Lock and session sensors
- ⏱️ Local countdown updates
- 📋 Task and task-point information
- 💬 Conversation and messaging support
- 🎛️ Lock controls and time adjustments
- 🖥️ Built-in Lovelace dashboard card
- ⚡ Home Assistant events for supported actions and API responses
- 📦 HACS-compatible installation

## 📋 Requirements

- Home Assistant with support for custom integrations
- A Chaster account
- A Chaster developer/API token
- Network access to the Chaster API
- [HACS](https://hacs.xyz/) — recommended

## 🚀 Installation

### HACS

1. Open **HACS → Integrations**.
2. Search for **Chaster** and select **Download**.
3. Restart Home Assistant.
4. Open **Settings → Devices & services**.
5. Select **Add Integration**.
6. Search for **Chaster** and complete setup.

If the integration is not yet listed in HACS, add this repository as a custom repository:

`https://github.com/jonny5509/Chaster-ha`

### Manual installation

1. Download or clone this repository.
2. Copy `custom_components/chaster` to your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add Integration**.
5. Search for **Chaster** and complete setup.

## ⚙️ Configuration

Configuration is performed through the Home Assistant UI.

You will need your **Chaster developer/API token**. Depending on the options and permissions available to your account, the integration can expose role information, shared locks, messaging, lock actions, and other supported features.

### 🔑 Token security

Treat your API token like a password.

- Never publish it in Git repositories.
- Do not include it in screenshots or support requests.
- Avoid exposing it in logs or configuration backups shared publicly.
- Rotate the token if you believe it has been compromised.

## 📊 Entities

### Sensors

- Wearer Username
- Keyholder Username
- Lock Title
- Lock Type
- Start Date / End Date
- Time Locked / Time Remaining
- Session Role
- Task Points
- Task Points Required
- Task Points Remaining

### Binary sensors

- Locked
- Ready to unlock
- Frozen
- Task Assigned

### Buttons

- Refresh
- Refresh history
- Unlock
- Emergency unlock
- Archive
- Freeze / Unfreeze
- Add 1 day / Add 1 hour
- Subtract 1 day / Subtract 1 hour

> Availability depends on the active session, role, lock state, configured options, and permissions granted by Chaster.

## 🛠️ Services

| Service | Purpose |
| --- | --- |
| `chaster.add_time` | Add time to a lock |
| `chaster.remove_time` | Remove time from a lock |
| `chaster.lock_action` | Send a supported lock action |
| `chaster.api_request` | Make a documented API request |
| `chaster.send_message` | Send a conversation message |

Example:

```yaml
action: chaster.add_time
data:
  lock_id: LOCK_ID
  seconds: 3600
```

## ⏱️ Countdown behaviour

**Time Locked** and **Time Remaining** update locally every second once the integration has received the required session data.

This does **not** make an API request every second. API communication continues to use the integration's normal polling/update mechanism.

## 🖥️ Lovelace dashboard card

Use the built-in card with:

```yaml
type: custom:chaster-card
```

The card can display countdown information, task points, common lock controls, and time-adjustment controls.

## 🌐 Chaster API

This integration uses the Chaster Public API for supported authentication, lock, task, conversation, history, and lock-action functionality.

For API details, scopes, and permissions, refer to the official Chaster documentation:

- [Getting started](https://docs.chaster.app/api/basics/getting-started/)
- [Developer tokens](https://docs.chaster.app/api/public-api/developer-token/)
- [Public API endpoints](https://docs.chaster.app/api/public-api/endpoints/)

## 🧰 Troubleshooting

### Authentication fails

Verify the developer token, required scopes, and Home Assistant's network connection to the Chaster API.

### Entities are unavailable

Some entities require an active session, a specific role, or information that is not currently available from Chaster.

### A button or service is unavailable

Availability can depend on the current lock state, role, configured options, and Chaster permissions.

### Countdown is not updating

Restart Home Assistant and check the logs for errors from `custom_components.chaster`.

## 👩‍💻 Development

Integration source code is located in `custom_components/chaster/`.

Important components include:

- `api.py`
- `config_flow.py`
- `coordinator.py`
- `sensor.py`
- `binary_sensor.py`
- `button.py`
- `www/chaster-card.js`

Contributions and bug reports are welcome through GitHub issues and pull requests.

## 🔄 Updating

For HACS installations:

1. Update **Chaster** from HACS.
2. Restart Home Assistant.
3. Reload the dashboard if the card does not immediately reflect the update.

Existing installations may require reauthentication or reconfiguration if the API credentials or configuration flow changes.

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## 🔗 Links

- [Repository](https://github.com/jonny5509/Chaster-ha)
- [Issues](https://github.com/jonny5509/Chaster-ha/issues)
- [Chaster API documentation](https://docs.chaster.app/api/)
