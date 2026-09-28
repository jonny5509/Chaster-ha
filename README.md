# Chaster for Home Assistant

A HACS-compatible Home Assistant custom integration for the [Chaster](https://chaster.app/) Public API.

The integration connects Home Assistant to Chaster using a developer/API token and exposes lock status, countdowns, task progress, role information, action controls, services, and Home Assistant events.

> **Important:** Chaster remains the authority for authentication, API scopes, lock permissions, timer restrictions, and safety restrictions. This integration does not bypass Chaster permissions or server-side checks.

## Features

- 🔐 Developer-token authentication through the Home Assistant config flow
- 🔄 Token validation during setup and reauthentication when credentials are rejected
- 👤 Role modes: Auto, Wearer, Keyholder, and Both
- 🔒 Wearer and keyholder lock views
- 🕒 Local countdown sensors that update every second without an API request every second
- 📅 Lock start/end dates and timer visibility
- 🏷️ Lock title and lock type
- ⭐ Tasks extension progress: Task Points, Task Points Required, Task Points Remaining, and Task Assigned
- 👤 Wearer/keyholder username sensors
- 🔐 Session-role sensors
- 🔘 State/permission-aware controls: Refresh, Refresh history, Unlock, Emergency unlock, Archive, Freeze, and Unfreeze
- ⚡ Add/remove lock time services
- 🧩 Generic Chaster API request and lock-action services
- 💬 Chaster conversation and messaging support
- 🔗 Optional shared-lock support
- 📡 Home Assistant events for API responses, actions, messages, and history
- 🧹 Cleanup of obsolete entities from older versions
- 🖥️ Built-in Chaster Card Lovelace custom card

## Requirements

- [Home Assistant](https://www.home-assistant.io/)
- [HACS](https://hacs.xyz/) for the recommended installation method
- A Chaster account
- A Chaster developer/API token with the scopes required for the features you want to use
- Network access from Home Assistant to https://api.chaster.app

## Installation

### HACS

1. Open **HACS → Integrations**.
2. Search for **Chaster**.
3. Install the integration.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services**.
6. Select **Add Integration**.
7. Search for **Chaster**.
8. Enter your Chaster developer token.

The repository is configured for HACS with content kept under custom_components and README rendering enabled.

### Manual

Copy the custom_components/chaster directory into:

~~~
/config/custom_components/chaster
~~~

Restart Home Assistant and add **Chaster** from **Settings → Devices & services**.

## Authentication

The integration uses a **Chaster developer token**.

It does **not** use OAuth, browser login, client IDs, client secrets, or OAuth callbacks.

### Creating a developer token

1. Open the [Chaster developer area](https://chaster.app/developers).
2. Request API access if required for your account.
3. Open the Chaster Developer interface.
4. Create or open an application.
5. Select **Tokens**.
6. Generate a developer token.
7. Copy the token into the Home Assistant Chaster configuration flow.

**Keep the token private.** Never publish it in GitHub issues, screenshots, logs, forums, Discord, or configuration examples.

During setup the integration validates the token using the Chaster profile endpoint. If the token is rejected later, Home Assistant can start the reauthentication flow so the stored token can be replaced.

## Configuration

After installation, open:

**Settings → Devices & services → Chaster → Configure**

Available options:

| Option | Description |
| --- | --- |
| **Polling interval** | Requested interval for Chaster API refreshes. |
| **Role mode** | Auto, Wearer, Keyholder, or Both. |
| **Enable keyholder features** | Enables keyholder-related API data and entities. |
| **Enable shared locks** | Enables shared-lock requests. |
| **Enable messaging** | Enables conversation/message polling. |
| **Enable lock actions** | Enables actions that can modify or control locks. |

### Polling interval

The configured polling interval accepts values from **30 to 3600 seconds**.

Countdown sensors update their displayed state locally once per second. The coordinator performs API polling separately, so the one-second countdown does not mean Chaster is queried every second.

## Roles and devices

The integration provides two role-specific Home Assistant device views:

- **Chaster - My lock**
- **Chaster - Keyholder**

Role availability depends on the selected role mode and the permissions/data returned by Chaster.

A **Session Role** sensor is exposed for each role view.

## Sensors

The current integration provides the following sensors for the relevant role.

### Identity and lock information

- **Wearer Username**
- **Keyholder Username**
- **Lock Title**
- **Lock Type**
- **Start Date**
- **End Date**
- **Timer Visible**
- **Session Role**

The Lock Title sensor also exposes attributes including the current lock ID, role, and lock status when a lock is active.

### Countdown sensors

- **Time Locked**
- **Time Remaining**

Countdown values are displayed as:

~~~
HH:MM:SS
~~~

These values are calculated locally from the lock timestamps and refreshed by Home Assistant every second.

### Task sensors

- **Task Points**
- **Task Points Required**
- **Task Points Remaining**

Task points are derived from the active lock and recognized Tasks extension action history.

If Chaster does not expose a task-point target in the available data, the required/remaining sensors fall back to 0.

## Binary sensors

For both wearer and keyholder views:

- **Locked**
- **Ready to unlock**
- **Frozen**
- **Task Assigned**

### Locked

Indicates whether the integration considers the current role's lock active.

### Ready to unlock

Becomes active when an active lock has a valid end/unlock timestamp, the timer has expired, and the current lock state supports unlocking.

### Frozen

Reflects the lock's frozen state when exposed by Chaster.

### Task Assigned

Uses the latest recognized Tasks action in the role-specific lock history. A task is considered assigned when the latest recognized Tasks action is an assignment rather than a completion or failure.

## Buttons

The integration creates role-specific buttons for:

- **Refresh**
- **Refresh history**
- **Unlock**
- **Emergency unlock**
- **Archive**
- **Freeze**
- **Unfreeze**

Button availability is evaluated against the current lock state, selected integration options, and available permissions.

### Refresh

Requests an immediate coordinator refresh.

### Refresh history

Retrieves lock history and fires the chaster_history Home Assistant event.

### Unlock

Normal unlock is protected against stale Home Assistant state.

Before sending the unlock request, the integration fetches the current lock details and verifies the current end time. If the timer has not expired, the unlock request is blocked locally.

Chaster also performs its own authoritative permission check.

### Emergency unlock

Emergency unlock is exposed only where the integration's role/action rules allow it and remains subject to Chaster's server-side permissions.

### Archive

Archives an eligible lock. The integration also removes the archived lock from local coordinator data before refreshing so obsolete action controls do not remain available.

### Freeze / Unfreeze

These actions are exposed when the current lock state supports the operation and **Enable lock actions** is enabled.

Chaster remains responsible for the final permission check.

## Services

All services use the chaster domain.

### chaster.add_time

Adds seconds to a Chaster lock.

The service accepts **1 to 31,536,000 seconds**.

~~~yaml
action: chaster.add_time
data:
  lock_id: LOCK_ID
  seconds: 3600
~~~

### chaster.remove_time

Removes seconds from a Chaster lock.

~~~yaml
action: chaster.remove_time
data:
  lock_id: LOCK_ID
  seconds: 600
~~~

The integration sends the corresponding positive or negative duration to Chaster. Chaster decides whether the requested change is permitted.

### chaster.lock_action

Calls a Chaster lock-action endpoint.

~~~yaml
action: chaster.lock_action
data:
  lock_id: LOCK_ID
  path: /locks/{lock_id}/...
  method: POST
  body: {}
~~~

Supported methods:

- POST
- PUT
- PATCH
- DELETE

The {lock_id} placeholder is replaced with the supplied lock ID. Lock actions must be enabled in the integration options.

### chaster.api_request

Provides a generic interface to Chaster Public API endpoints available to the authenticated developer token.

~~~yaml
action: chaster.api_request
data:
  method: GET
  path: /permissions/definitions
  params: {}
  body: {}
~~~

Supported methods:

- GET
- POST
- PUT
- PATCH
- DELETE

API paths must begin with /. Use the official Chaster API documentation as the source of truth for endpoint paths, request parameters, request bodies, scopes, permissions, and response formats.

### chaster.send_message

Sends a message through a Chaster conversation endpoint.

~~~yaml
action: chaster.send_message
data:
  path: /conversations/CONVERSATION_ID
  body:
    # documented Chaster message payload
~~~

If path is omitted, the service defaults to /conversations.

Messaging must be enabled in the integration options for the normal conversation polling path. The service uses the configured developer token and remains subject to Chaster permissions.

## Home Assistant events

### chaster_api_response

Fired after a successful chaster.api_request call. The event contains the requested method/path and API result.

### chaster_action

Fired after a successful generic lock action or time change.

Example:

~~~yaml
lock_id: LOCK_ID
action: add_time
seconds: 3600
result: ...
~~~

For chaster.lock_action, the event contains the lock ID, resolved path, and API result.

### chaster_message

Fired after a successful chaster.send_message call. The event contains the API result.

### chaster_history

Fired when a role-specific **Refresh history** button retrieves lock history. The event contains:

- lock_id
- role
- history

## Built-in Chaster Card

The repository includes a Lovelace custom card at:

~~~
custom_components/chaster/www/chaster-card.js
~~~

The integration registers the card automatically at:

~~~
/chaster/chaster-card.js
~~~

After installing/updating the integration and restarting Home Assistant, the card can be used as:

~~~yaml
type: custom:chaster-card
~~~

The current card displays:

- Time locked
- Time remaining
- Maximum remaining, when a matching entity is available
- Task points
- Refresh
- Refresh history
- Unlock
- Emergency unlock

The card discovers matching Chaster entities from Home Assistant and invokes the corresponding button services.

## API coverage

The internal API client currently provides helpers for:

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

The generic chaster.api_request service can also be used for documented Chaster Public API endpoints that do not have a dedicated helper.

## Permissions and safety

This integration is intentionally permission-aware, but it is **not** a replacement for Chaster's authorization system.

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

For normal unlock, the integration additionally verifies the current lock end time immediately before sending the unlock request.

## Data refresh behaviour

The integration uses Home Assistant's DataUpdateCoordinator.

Depending on the selected options and role, coordinator data can include:

- Profile information
- Wearer locks
- Keyholder lock search results
- Shared locks
- Conversations
- Current lock details
- Active keyholder lock details
- Role-specific lock history

Optional permission-scoped data can be preserved when an optional endpoint temporarily becomes unavailable, allowing the integration to continue operating without treating every optional permission failure as a complete integration failure.

### Countdown refresh

Countdown sensors use a local one-second Home Assistant timer:

- No Chaster API request is made every second.
- The sensor recalculates its displayed value locally.
- The coordinator continues API refreshes separately.

## Existing installations and upgrades

The integration stores the developer token under the config-entry data key token.

The current config flow is developer-token based and has been migrated away from older authentication/entity models.

When upgrading an existing installation:

1. Restart Home Assistant after installing the new integration files.
2. Open **Settings → Devices & services → Chaster**.
3. Reconfigure the integration if Home Assistant requests it.
4. If the previous installation used an older authentication model, remove the old Chaster entry and add it again with a developer token.

The integration includes cleanup logic for obsolete entities, including legacy **Obedience connected**, history, dynamic lock, and older keyholder entities.

## Troubleshooting

### Integration does not load after an update

Perform a full Home Assistant restart rather than only reloading an individual entity platform.

Then check:

**Settings → System → Logs**

for errors containing:

~~~
custom_components.chaster
~~~

### Token rejected

Generate a new Chaster developer token and use the integration's reauthentication flow or reconfigure the integration.

Do not paste the token into a public issue or log.

### A button is unavailable

Button availability depends on:

- Selected role
- Presence of a suitable active/eligible lock
- Current lock status
- Lock timer
- **Enable lock actions** setting
- Permissions returned by Chaster
- The specific action's role restrictions

Normal **Unlock** is intentionally unavailable until the timer has expired and is rechecked against the current Chaster lock immediately before the request.

### Countdown is not ticking

Countdown sensors are designed to update locally every second.

If they are not changing:

1. Confirm the integration loaded without Python/import errors.
2. Restart Home Assistant fully.
3. Check the Chaster entities under **Settings → Devices & services**.
4. Review Home Assistant logs for errors from custom_components.chaster.

### Service UI errors

Service definitions are stored in:

~~~
custom_components/chaster/services.yaml
~~~

The service schemas use Home Assistant selectors for text, numbers, HTTP methods, and JSON objects.

## Development

The integration source is located in:

~~~
custom_components/chaster/
~~~

Important modules include:

| File | Purpose |
| --- | --- |
| custom_components/chaster/__init__.py | Config-entry setup, services, events, and static card registration |
| custom_components/chaster/api.py | Authenticated Chaster Public API client |
| custom_components/chaster/config_flow.py | Developer-token setup, reauthentication, and options |
| custom_components/chaster/const.py | Integration constants, options, roles, and API base URL |
| custom_components/chaster/coordinator.py | API polling and shared integration state |
| custom_components/chaster/entity.py | Shared Home Assistant entity behaviour |
| custom_components/chaster/sensors.py | Lock, identity, countdown, and task sensors |
| custom_components/chaster/sensor.py | Sensor platform compatibility/setup |
| custom_components/chaster/binary_sensor.py | Lock, unlock-ready, frozen, and task state |
| custom_components/chaster/button.py | Refresh and lock-action buttons |
| custom_components/chaster/services.yaml | Home Assistant service descriptions |
| custom_components/chaster/translations/en.json | Config-flow and options UI text |
| custom_components/chaster/www/chaster-card.js | Built-in Lovelace Chaster Card |
| custom_components/chaster/brand/icon.png | Integration icon |

The repository is intended for Home Assistant and HACS.

Recommended validation includes:

- Home Assistant **hassfest**
- HACS validation
- Python compilation/static checks
- A Home Assistant test environment for runtime verification

## Repository

Source code and issue tracking:

- GitHub: https://github.com/jonny5509/Chaster-ha
- Issues: https://github.com/jonny5509/Chaster-ha/issues

## Official Chaster documentation

Use Chaster's documentation as the authoritative reference for API behaviour, scopes, permissions, endpoint paths, payloads, and response formats:

- [Getting started](https://docs.chaster.app/api/basics/getting-started/)
- [Developer tokens](https://docs.chaster.app/api/public-api/developer-token/)
- [Public API endpoints](https://docs.chaster.app/api/public-api/endpoints/)
- [API scopes](https://docs.chaster.app/api/reference/scopes/)
- [Tasks API](https://docs.chaster.app/api/extensions-api/interact-with-extensions/tasks/)
- [Tasks extension](https://docs.chaster.app/extensions/tasks/)
- [Action logs](https://docs.chaster.app/api/reference/action-logs/)

## License

MIT License. See [LICENSE](LICENSE).
