# Chaster for Home Assistant

A Home Assistant custom integration for the Chaster Public API.

Monitor your Chaster lock, countdowns, tasks, and session information from Home Assistant.

## Features

- HACS-compatible custom integration
- Home Assistant Config Flow setup
- Developer/API token authentication
- Wearer and keyholder support
- Lock, session, and task sensors
- Local countdown updates
- Lock controls and time adjustments
- Conversation and messaging support
- Built-in Lovelace dashboard card
- Home Assistant events for actions and API responses

## Requirements

- Home Assistant
- A Chaster account
- A Chaster developer/API token
- Network access to the Chaster API
- [HACS](https://hacs.xyz/) — recommended

## Installation

### HACS

1. Open **HACS → Integrations**.
2. Search for **Chaster** and install it.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add Integration**.
5. Search for **Chaster** and complete setup.

If it is not listed, add `https://github.com/jonny5509/Chaster-ha` as a custom repository.

### Manual

Copy `custom_components/chaster` into `config/custom_components/`, restart Home Assistant, then add **Chaster** from **Settings → Devices & services**.

## Configuration

Setup is handled through the Home Assistant UI.

You will need your **Chaster developer/API token**. Options include polling interval, role mode, keyholder features, shared locks, messaging, and lock actions.

### Token security

Treat your API token like a password. Do not share it, commit it to Git, or include it in public screenshots, logs, or configuration files.

## Entities

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
- Freeze
- Unfreeze
- Add 1 day
- Add 1 hour
- Subtract 1 day
- Subtract 1 hour

Availability depends on the current session, role, lock state, options, and Chaster permissions.

## Services

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

## Countdown

**Time Locked** and **Time Remaining** update locally every second. This does not make an API request every second.

## Dashboard Card

Use the built-in card with:

```yaml
type: custom:chaster-card
```

It can display countdowns, task points, common lock controls, and 1-hour/1-day time adjustment controls.

## API

The integration uses the Chaster Public API for authentication, locks, tasks, conversations, history, and supported lock actions.

See the official documentation for endpoints, scopes, and permissions:

- [Getting started](https://docs.chaster.app/api/basics/getting-started/)
- [Developer tokens](https://docs.chaster.app/api/public-api/developer-token/)
- [Public API endpoints](https://docs.chaster.app/api/public-api/endpoints/)

## Troubleshooting

### Authentication fails

Check your developer token, required scopes, and Home Assistant's connection to the Chaster API.

### Entities are unavailable

Some entities require an active session or specific role/lock information.

### A button is unavailable

Availability depends on the current lock state, role, options, and Chaster permissions.

### Countdown is not updating

Restart Home Assistant and check the logs for `custom_components.chaster` errors.

## Development

The integration is located in `custom_components/chaster/`.

Key files include `api.py`, `config_flow.py`, `coordinator.py`, `sensor.py`, `binary_sensor.py`, `button.py`, and `www/chaster-card.js`.

## Existing Installations

Update through HACS or replace the integration files, then restart Home Assistant. Reauthenticate or reconfigure if requested.

## Repository

[GitHub repository](https://github.com/jonny5509/Chaster-ha)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
