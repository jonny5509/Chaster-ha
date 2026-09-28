# Chaster for Home Assistant

A HACS custom integration that connects Home Assistant to the Chaster Public API using a Chaster developer token.

It exposes Chaster lock information, countdowns, task progress, role-specific status, messaging, history, permissions, and lock-control actions as Home Assistant entities and services.

> **Important:** Chaster remains the authority for account permissions, lock permissions, safety restrictions, and whether an action is allowed. This integration does not bypass Chaster API scopes or lock restrictions.

## Features

- 🔐 Developer-token authentication through the Home Assistant config flow
- 🔄 Token validation during setup and automatic reauthentication when credentials are rejected
- 👤 Role modes:
  - **Auto** — detect available wearer/keyholder access
  - **Wearer**
  - **Keyholder**
  - **Both**
- 🔒 Current lock data for wearer and keyholder views
- 🕒 Countdown sensors:
  - **Time Locked**
  - **Time Remaining**
  - **Maximum Time Remaining**
- ⚡ Countdown values are recalculated locally every second, without making a Chaster API request every second
- ⭐ Task progress:
  - **Task Points**
  - **Task Points Required**
  - **Task Points Remaining**
- 👤 Username, lock-title, and session-role sensors
- 🔗 Optional shared-lock data
- 💬 Optional conversation/messaging support
- 🔘 Lock-control buttons:
  - Refresh
  - Refresh history
  - Unlock
  - Emergency unlock
  - Archive
  - Freeze
  - Unfreeze
- ➕ Time adjustment services
- 🧩 Generic Chaster API request and lock-action services
- 📡 Home Assistant events for API responses, actions, messages, and history
- 🔐 Permission-aware action availability
- 🧹 Automatic cleanup of obsolete entities from older versions

## Requirements

- Home Assistant
- HACS, if installing through HACS
- A Chaster account
- A Chaster developer/API token with the scopes required for the features you want to use
- Network access from Home Assistant to the Chaster API

## Installation

### HACS

1. Open **HACS → Integrations**.
2. Search for **Chaster**.
3. Install the integration.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add Integration**.
6. Search for **Chaster**.
7. Enter your Chaster developer token.

### Manual

Copy the `custom_components/chaster` directory into:

```text
/config/custom_components/chaster
```

Restart Home Assistant and add **Chaster** from **Settings → Devices & services**.

## Authentication

The integration uses a **Chaster developer token**. It does not use OAuth, browser login, client IDs, client secrets, or OAuth callbacks.

### Creating a developer token

1. Open the Chaster developer area.
2. Request API access if required for your account.
3. Open the **Developer interface**.
4. Create or open an application.
5. Open **Tokens**.
6. Generate a developer token.
7. Copy the token into the Home Assistant Chaster configuration flow.

**Keep the token private.** Do not publish it in GitHub issues, screenshots, logs, forums, Discord, or configuration examples.

### Token validation

During setup, the integration validates the token against the Chaster profile endpoint.

If Chaster returns an authentication/authorization failure, Home Assistant can request reauthentication so the stored token can be replaced.

## Configuration

After installation, open:

**Settings → Devices & services → Chaster → Configure**

The options are:

| Option | Description |
| --- | --- |
| **Polling interval** | Requested interval for Chaster API refreshes. |
| **Role mode** | Auto, Wearer, Keyholder, or Both. |
| **Keyholder features** | Enables keyholder-related API data and entities. |
| **Shared locks** | Enables shared-lock requests. |
| **Messaging** | Enables conversation/message data. |
| **Lock actions** | Enables actions that can modify or control locks. |

### Polling interval

The configuration accepts **30–3600 seconds**.

The current coordinator intentionally caps the actual API refresh interval at **10 seconds**. This keeps action availability responsive, particularly around timer expiry, while the countdown sensors themselves update locally every second.

**Important:** a one-second countdown display does **not** mean the integration sends an API request every second.

## Roles and devices

The integration supports two role views:

- **Wearer / My lock**
- **Keyholder**

Depending on role mode and the permissions returned by Chaster, Home Assistant can expose entities for one or both roles.

The integration also tracks the detected role in coordinator data and exposes a **Session Role** sensor for the relevant view.

## Sensors

The integration provides role-specific sensors where applicable.

### Identity and lock information

- **Wearer Username**
- **Keyholder Username**
- **Lock Title**
- **Session Role**

### Countdown sensors

- **Time Locked**
- **Time Remaining**
- **Maximum Time Remaining**

Countdown values are represented as `HH:MM:SS`.

The displayed countdown is recalculated locally once per second. Chaster API data is refreshed separately by the coordinator.

### Task sensors

- **Task Points**
- **Task Points Required**
- **Task Points Remaining**

Task-point information is derived from the available Chaster lock/extension data.

If the task-point configuration is unavailable, the required/remaining task-point sensors fall back to `0`.

## Binary sensors

For wearer and keyholder views, the integration provides:

- **Locked**
- **Ready to unlock**
- **Frozen**
- **Task Assigned**

### Locked

Indicates whether the current role's active lock is considered active by the integration.

### Ready to unlock

Becomes active when the lock timer has expired while the lock remains in a lock state that supports unlocking.

### Frozen

Reflects the lock's frozen state when that state is exposed by Chaster.

### Task Assigned

Uses the role-specific lock history and the latest recognized Tasks action to determine whether a task is currently assigned.

## Buttons

The integration creates role-specific action buttons for:

- **Refresh**
- **Refresh history**
- **Unlock**
- **Emergency unlock**
- **Archive**
- **Freeze**
- **Unfreeze**

Button availability is evaluated against the current lock state and integration settings.

### Refresh

Requests an immediate coordinator refresh.

### Refresh history

Retrieves the current lock history and fires the `chaster_history` Home Assistant event.

### Unlock

Normal unlock is only made available after the lock timer has expired.

Before sending the unlock request, the integration fetches the current lock detail and verifies the timer again. This prevents a stale Home Assistant state from being used to unlock an active timer.

### Emergency unlock

Emergency unlock is restricted to the wearer role by the integration and remains subject to Chaster's own permissions.

### Archive

Archives an eligible unlocked lock. The integration also removes the archived lock from its local coordinator data before refreshing, so the obsolete Archive action does not remain available unnecessarily.

### Freeze / Unfreeze

These actions are only made available when the current lock state supports the corresponding operation and lock actions are enabled.

Chaster remains responsible for the final permission check.

## Services

All service names use the `chaster` domain.

### `chaster.add_time`

Adds seconds to a known Chaster lock.

The service accepts between **1 and 31,536,000 seconds**.

```yaml
action: chaster.add_time
data:
  lock_id: LOCK_ID
  seconds: 3600
```

### `chaster.remove_time`

Removes seconds from a known Chaster lock.

The service accepts between **1 and 31,536,000 seconds**.

```yaml
action: chaster.remove_time
data:
  lock_id: LOCK_ID
  seconds: 600
```

The integration sends the corresponding positive or negative duration to Chaster. Chaster decides whether the requested change is permitted.

### `chaster.lock_action`

Calls a Chaster lock-action endpoint for a known lock.

```yaml
action: chaster.lock_action
data:
  lock_id: LOCK_ID
  path: /locks/{lock_id}/...
  method: POST
  body: {}
```

Supported methods are:

- POST
- PUT
- PATCH
- DELETE

The `{lock_id}` placeholder in the path is replaced with the supplied lock ID.

Lock actions must be enabled in the integration options.

### `chaster.api_request`

Provides a generic interface to documented Chaster Public API endpoints.

```yaml
action: chaster.api_request
data:
  method: GET
  path: /permissions/definitions
  params: {}
  body: {}
```

Supported methods are:

- GET
- POST
- PUT
- PATCH
- DELETE

API paths must begin with `/`.

Use the official Chaster API documentation as the source of truth for endpoint paths, request parameters, request bodies, permissions, and response formats.

### `chaster.send_message`

Sends a message through a Chaster conversation endpoint.

```yaml
action: chaster.send_message
data:
  path: /conversations/CONVERSATION_ID
  body:
    # documented Chaster message payload
```

If `path` is omitted, the service defaults to `/conversations`.

Messaging data must be enabled in the integration options for the normal conversation polling path. The service itself uses the configured Chaster developer token and remains subject to Chaster permissions.

## Home Assistant events

The integration fires these events on the Home Assistant event bus.

### `chaster_api_response`

Fired after a successful `chaster.api_request` call.

Example:

```yaml
method: GET
path: /permissions/definitions
result: ...
```

### `chaster_action`

Fired after a successful generic lock action or time change.

Example:

```yaml
lock_id: LOCK_ID
action: add_time
seconds: 3600
result: ...
```

For `chaster.lock_action`, the event contains the lock ID, resolved path, and API result.

### `chaster_message`

Fired after a successful `chaster.send_message` call.

The event contains the API result.

### `chaster_history`

Fired when a role-specific **Refresh history** button retrieves lock history.

The event contains:

- `lock_id`
- `role`
- `history`

## API coverage

The internal API client currently provides helpers for:

- Profile
- Wearer locks
- Individual lock details
- Keyholder lock search
- Lock extensions
- Lock extension actions
- Shared locks
- Conversations
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

The generic `chaster.api_request` service can also be used for documented endpoints that do not have a dedicated helper.

## Permissions and safety

The integration is intentionally permission-aware, but it is not a replacement for Chaster's authorization system.

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

For normal unlock, the integration additionally verifies the lock's current end time immediately before sending the request.

## Data refresh behaviour

The integration uses Home Assistant's `DataUpdateCoordinator`.

The coordinator refreshes:

- Profile information
- Wearer locks when requested
- Keyholder lock search results when enabled/requested
- Shared locks when enabled
- Conversations when messaging is enabled
- Current lock details
- Active keyholder lock details
- Role-specific history for active locks

The coordinator preserves some previously known data when a permission-scoped endpoint temporarily becomes unavailable, allowing the integration to continue operating without treating every optional permission failure as a complete integration failure.

### Countdown refresh

The three countdown sensors use a local Home Assistant one-second timer:

- No Chaster API request is made every second.
- The sensor recalculates its displayed state locally.
- The coordinator continues to provide fresh Chaster data separately.

## Existing installations and upgrades

The integration stores the developer token under the config-entry data key `token`.

The current configuration flow is developer-token based.

When upgrading from an older version that used a different authentication or entity model:

1. Restart Home Assistant after installing the new files.
2. Check **Settings → Devices & services → Chaster**.
3. Reconfigure the integration if Home Assistant requests reauthentication.
4. If an old installation used OAuth-based authentication, remove the old Chaster entry and add it again with a developer token.

The integration contains cleanup logic for obsolete Chaster entities, including the old **Obedience connected** entity and legacy lock/history entities.

## Troubleshooting

### Integration does not load after an update

Fully restart Home Assistant rather than only reloading an individual entity platform.

Then check:

**Settings → System → Logs**

for errors mentioning:

```text
custom_components.chaster
```

### Token rejected

Generate a new Chaster developer token and use the integration's reauthentication flow or reconfigure the integration.

Do not paste the token into a public issue.

### A button is unavailable

Button availability depends on:

- The selected role
- Whether a suitable active/eligible lock is present
- The current lock status
- The lock timer
- The **Lock actions** option
- The permissions returned by Chaster
- The specific action's role restrictions

For example, normal **Unlock** is intentionally unavailable until the timer has expired.

### Countdown is not ticking

The countdown sensors are designed to update locally every second. If they are not changing:

1. Check that the integration loaded without Python/import errors.
2. Restart Home Assistant fully.
3. Check the Chaster integration entities in **Settings → Devices & services**.
4. Review the Home Assistant logs for errors from `custom_components.chaster`.

### Service UI errors

The service definitions are stored in:

```text
custom_components/chaster/services.yaml
```

JSON-style service fields use Home Assistant object selectors.

## Development

Source code lives in:

```text
custom_components/chaster/
```

Important modules include:

- `__init__.py` — config-entry setup and service registration
- `api.py` — authenticated Chaster API client
- `config_flow.py` — token setup, reauthentication, and options
- `coordinator.py` — API polling and shared integration state
- `sensors.py` — sensor entities and local countdown refresh
- `binary_sensor.py` — lock/task state entities
- `button.py` — refresh and lock-action buttons
- `services.yaml` — Home Assistant service descriptions

The project is intended for Home Assistant and HACS.

Recommended validation includes:

- Home Assistant **hassfest**
- HACS validation
- Python compilation/static checks
- A Home Assistant test environment for runtime verification

## Repository

Source code and issue tracking:

- GitHub: https://github.com/jonny5509/Chaster-ha

## Official Chaster documentation

Use Chaster's documentation as the authoritative reference for API behaviour, scopes, permissions, endpoint paths, payloads, and response formats:

- Getting started: https://docs.chaster.app/api/basics/getting-started/
- Developer tokens: https://docs.chaster.app/api/public-api/developer-token/
- Public API endpoints: https://docs.chaster.app/api/public-api/endpoints/
- API scopes: https://docs.chaster.app/api/reference/scopes/
- Tasks API: https://docs.chaster.app/api/extensions-api/interact-with-extensions/tasks/
- Tasks extension: https://docs.chaster.app/extensions/tasks/
- Action logs: https://docs.chaster.app/api/reference/action-logs/

## License

MIT License. See [LICENSE](LICENSE).
