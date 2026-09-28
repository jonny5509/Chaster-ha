# Chaster for Home Assistant

A Home Assistant custom integration for the Chaster Public API.

Chaster connects Home Assistant to your Chaster account using a developer/API token. It provides lock and session information, countdowns, task progress, role information, controls, API-backed services, Home Assistant events, and a built-in Lovelace card.

## Features

- HACS-compatible custom integration
- Home Assistant Config Flow setup
- Chaster developer-token authentication
- Automatic token validation and reauthentication
- Wearer and keyholder role support
- Auto, Wearer, Keyholder, and Both role modes
- Lock and session information exposed as Home Assistant entities
- Local one-second countdown updates without API requests every second
- Task points and task assignment information
- Refresh controls for the current session and lock history
- Lock controls including unlock, emergency unlock, archive, freeze, and unfreeze
- Add/remove lock time services
- Generic Chaster API request service
- Generic lock-action service
- Conversation and messaging support
- Shared-lock support
- Home Assistant events for API responses, actions, messages, and history
- Built-in Chaster Lovelace dashboard card
- Cleanup and migration support for older installations
- Home Assistant Hassfest/HACS-friendly project structure

## Requirements

- Home Assistant with support for custom integrations
- [HACS](https://hacs.xyz/) for the recommended installation method
- A Chaster account
- A Chaster developer/API token with the scopes required for the features you want to use
- Network access from Home Assistant to the Chaster API

## Installation

### HACS

1. Open **HACS → Integrations** in Home Assistant.
2. Search for **Chaster**.
3. Install the integration.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add Integration**.
6. Search for **Chaster** and complete the setup flow.

If the repository is not listed in HACS, add this repository as a custom repository:

`https://github.com/jonny5509/Chaster-ha`

### Manual

1. Download or clone this repository.
2. Copy `custom_components/chaster` into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.
4. Add **Chaster** from **Settings → Devices & services**.

## Configuration

The integration is configured through the Home Assistant UI.

When adding Chaster, enter your **Chaster developer/API token**. The integration validates the token against the Chaster API before creating the config entry.

After installation, additional options can be configured from:

**Settings → Devices & services → Chaster → Configure**

Available options include:

- **Polling interval** — controls how often Chaster API data is refreshed.
- **Role mode** — Auto, Wearer, Keyholder, or Both.
- **Enable keyholder features** — enables keyholder-related data and entities.
- **Enable shared locks** — enables shared-lock support.
- **Enable messaging** — enables conversation/message polling.
- **Enable lock actions** — enables actions that can modify or control locks.

The polling interval accepts values from **30 to 3600 seconds**.

Countdown sensors update locally every second. This does **not** cause a Chaster API request every second.

### API token security

Treat your Chaster developer token like a password:

- Do not commit it to Git.
- Do not share it in screenshots, logs, issues, forums, or Discord.
- Do not include it in public configuration examples.
- Keep backups and exported Home Assistant configuration containing the token secure.

The integration does not use OAuth, browser login, client IDs, client secrets, or OAuth callbacks.

## Entities

Chaster provides role-specific Home Assistant device views:

- **Chaster - My lock**
- **Chaster - Keyholder**

Availability depends on the selected role mode, the current Chaster session, and the information and permissions returned by the API.

### Sensors

The integration currently provides:

- **Wearer Username**
- **Keyholder Username**
- **Lock Title**
- **Lock Type**
- **Start Date**
- **End Date**
- **Timer Visible**
- **Time Locked**
- **Time Remaining**
- **Session Role**
- **Task Points**
- **Task Points Required**
- **Task Points Remaining**

The Lock Title sensor also exposes useful lock attributes such as the current lock ID, role, and lock status.

### Binary sensors

For the relevant wearer/keyholder role:

- **Locked**
- **Ready to unlock**
- **Frozen**
- **Task Assigned**

### Buttons

The integration provides role-aware buttons for:

- **Refresh**
- **Refresh history**
- **Unlock**
- **Emergency unlock**
- **Archive**
- **Freeze**
- **Unfreeze**

Button availability depends on the current lock state, selected integration options, permissions, and the specific action's requirements.

## Countdown sensors

**Time Locked** and **Time Remaining** are calculated locally from the lock timestamps.

The displayed format is:

`HH:MM:SS`

Home Assistant updates these values every second while the coordinator continues to poll the Chaster API at the configured interval.

This avoids making a Chaster API request every second just to display a countdown.

## Task information

When the Tasks extension data is available, Chaster exposes:

- **Task Points**
- **Task Points Required**
- **Task Points Remaining**
- **Task Assigned**

Task information is derived from the active lock and recognized Tasks extension action history.

If Chaster does not provide a task-point target in the available data, the required and remaining values fall back to `0`.

## Services

All services use the `chaster` domain.

| Service | Purpose |
| --- | --- |
| `chaster.add_time` | Add time to a Chaster lock |
| `chaster.remove_time` | Remove time from a Chaster lock |
| `chaster.lock_action` | Send a supported Chaster lock action |
| `chaster.api_request` | Send a documented Chaster Public API request |
| `chaster.send_message` | Send a message through a Chaster conversation |

### Time controls

`chaster.add_time` accepts between **1 and 31,536,000 seconds**.

Example:

```yaml
action: chaster.add_time
data:
  lock_id: LOCK_ID
  seconds: 3600
```

`chaster.remove_time` uses a positive number of seconds and sends the corresponding negative adjustment.

### Generic lock action

`chaster.lock_action` can be used for supported lock-action endpoints.

```yaml
action: chaster.lock_action
data:
  lock_id: LOCK_ID
  path: /locks/{lock_id}/...
  method: POST
  body: {}
```

Supported methods:

- `POST`
- `PUT`
- `PATCH`
- `DELETE`

The `{lock_id}` placeholder is replaced with the supplied lock ID.

### Generic API request

`chaster.api_request` provides access to documented Chaster Public API endpoints that do not have a dedicated integration service.

```yaml
action: chaster.api_request
data:
  method: GET
  path: /permissions/definitions
  params: {}
  body: {}
```

Supported methods:

- `GET`
- `POST`
- `PUT`
- `PATCH`
- `DELETE`

API paths must begin with `/`.

Use the official Chaster API documentation as the source of truth for endpoint paths, parameters, payloads, scopes, permissions, and response formats.

### Messaging

`chaster.send_message` sends a message through a Chaster conversation endpoint.

```yaml
action: chaster.send_message
data:
  path: /conversations/CONVERSATION_ID
  body:
    # documented Chaster message payload
```

Messaging must be enabled in the integration options for normal conversation polling.

## Lock controls

The integration supports:

- Refresh
- Refresh history
- Normal unlock
- Emergency unlock
- Archive
- Freeze
- Unfreeze

Chaster remains responsible for the final server-side permission check.

### Normal unlock

Normal unlock is intentionally protected against stale Home Assistant state.

Before sending an unlock request, the integration retrieves the current lock details and verifies the current end time. If the timer has not expired, the request is blocked locally.

Chaster then performs its own authoritative permission check.

### Emergency unlock

Emergency unlock is exposed only when the integration's role and action rules allow it and remains subject to Chaster permissions.

### Freeze / Unfreeze

These actions are available when the current lock state supports them and **Enable lock actions** is enabled.

### Archive

When an eligible lock is archived, the integration removes the archived lock from local coordinator data before refreshing so obsolete action controls do not remain available.

## Home Assistant events

The integration can fire the following events.

### `chaster_api_response`

Fired after a successful `chaster.api_request` call.

The event includes the requested method/path and API result.

### `chaster_action`

Fired after a successful generic lock action or time change.

Example data:

```yaml
lock_id: LOCK_ID
action: add_time
seconds: 3600
result: ...
```

### `chaster_message`

Fired after a successful `chaster.send_message` call.

### `chaster_history`

Fired when **Refresh history** retrieves lock history.

The event includes:

- `lock_id`
- `role`
- `history`

## Dashboard card

The integration includes a built-in Lovelace card at:

`custom_components/chaster/www/chaster-card.js`

The card is registered automatically at:

`/chaster/chaster-card.js`

Use it in a dashboard with:

```yaml
type: custom:chaster-card
```

The card can display:

- Time locked
- Time remaining
- Maximum remaining, when available
- Task points
- Refresh
- Refresh history
- Unlock
- Emergency unlock

The card discovers matching Chaster entities from Home Assistant and invokes the corresponding button services.

## API

The integration communicates with the Chaster Public API.

Current API client support includes:

- Profile authentication
- Wearer locks
- Individual lock details
- Keyholder lock search
- Lock extensions
- Lock extension actions
- Shared locks
- Conversations
- Individual conversations
- Sending messages
- Creating conversations
- Adding/removing lock time
- Freeze/unfreeze
- Normal unlock
- Emergency unlock
- Archive
- Combination retrieval
- Lock history
- Lock settings
- Bondage configuration
- Permission definitions
- Keyholder notes

The generic `chaster.api_request` service can also be used for documented Chaster Public API endpoints that do not have a dedicated helper.

## Permissions and safety

The integration does not bypass Chaster authentication, authorization, or server-side restrictions.

It does not attempt to bypass:

- API scopes
- Lock permissions
- Minimum dates
- Maximum dates
- Timer restrictions
- History visibility
- Extension permissions
- Safety settings
- Freeze/unfreeze restrictions
- Unlock restrictions

Chaster performs the authoritative server-side permission check.

If Chaster rejects an operation, the integration does not override the response.

## Troubleshooting

### The integration cannot authenticate

Check that:

1. The developer/API token is correct.
2. The token has the required scopes.
3. The token has not been revoked or replaced.
4. Home Assistant can reach the Chaster API.

If the token becomes invalid, use the Home Assistant reauthentication flow or reconfigure the integration.

### The integration installs but entities are unavailable

Check the Home Assistant logs and confirm that Chaster is returning a valid profile/lock response.

Some entities depend on having a relevant Chaster session or lock.

### A button is unavailable

Button availability depends on:

- Selected role
- Current lock/session state
- Timer state
- **Enable lock actions**
- Chaster permissions
- The specific action's role restrictions

Normal **Unlock** remains unavailable until the timer has expired and is checked against the current Chaster lock.

### The countdown is not updating

Countdown sensors are designed to update locally every second.

If they are not changing:

1. Confirm the integration loaded without Python/import errors.
2. Restart Home Assistant fully.
3. Check the Chaster entities under **Settings → Devices & services**.
4. Review the Home Assistant logs for `custom_components.chaster` errors.

### Service UI errors

Service definitions are stored in:

`custom_components/chaster/services.yaml`

The service schemas use Home Assistant selectors for text, numbers, HTTP methods, and JSON objects.

## Development

The Home Assistant integration lives under:

`custom_components/chaster/`

Important components include:

- `__init__.py` — Config-entry setup, services, events, and card registration
- `api.py` — Chaster Public API client
- `config_flow.py` — Setup, options, and reauthentication
- `const.py` — Integration constants and API configuration
- `coordinator.py` — API polling and shared integration state
- `entity.py` — Shared entity behaviour
- `sensors.py` — Lock, identity, countdown, and task sensors
- `sensor.py` — Sensor platform setup
- `binary_sensor.py` — Lock and session binary sensors
- `button.py` — Refresh and lock-action buttons
- `services.yaml` — Home Assistant service descriptions
- `translations/en.json` — Config-flow and options UI text
- `www/chaster-card.js` — Dashboard card
- `brand/icon.png` — Integration icon

Recommended validation includes:

- Home Assistant **Hassfest**
- HACS validation
- Python compilation/static checks
- A Home Assistant test environment

## Existing installations

After updating the integration:

1. Update it through HACS or replace the integration files.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Chaster**.
4. Reconfigure or reauthenticate if Home Assistant requests it.

The integration stores the developer token in the config entry and includes migration/cleanup logic for obsolete entities from older versions.

## Repository

Source code, releases, and issue tracking:

`https://github.com/jonny5509/Chaster-ha`

## Official Chaster documentation

Use the official Chaster documentation as the authoritative reference for API behaviour, scopes, permissions, endpoints, payloads, and response formats:

- [Getting started](https://docs.chaster.app/api/basics/getting-started/)
- [Developer tokens](https://docs.chaster.app/api/public-api/developer-token/)
- [Public API endpoints](https://docs.chaster.app/api/public-api/endpoints/)
- [API scopes](https://docs.chaster.app/api/reference/scopes/)
- [Tasks API](https://docs.chaster.app/api/extensions-api/interact-with-extensions/tasks/)
- [Tasks extension](https://docs.chaster.app/extensions/tasks/)
- [Action logs](https://docs.chaster.app/api/reference/action-logs/)

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
