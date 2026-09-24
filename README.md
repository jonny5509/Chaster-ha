# Chaster for Home Assistant

A HACS custom integration for the [Chaster](https://chaster.app/) Public API, bringing your Chaster locks, timers, messages, permissions, and lock controls into Home Assistant.

> **Important:** Chaster remains the authority for account permissions and safety restrictions. This integration does not bypass Chaster permissions or API restrictions.

## Features

- 🔐 Developer-token authentication through the Home Assistant config flow
- 🔄 Automatic reauthentication when a token expires or is revoked
- 👤 Automatic role detection with:
  - **Auto**
  - **Wearer**
  - **Keyholder**
  - **Both**
- 🔒 Current-lock entity that follows the active lock
- 📜 Historical wearer and keyholder lock sensors
- 🤝 Shared-lock support when the Chaster account/API token has access
- 💬 Messaging data and a generic message service
- 🕒 Current-lock history diagnostics
- 🎛️ Lock controls for:
  - Refresh
  - Freeze
  - Unfreeze
  - Unlock
  - Emergency unlock
  - Archive
- ➕ `chaster.add_time` service
- ➖ `chaster.remove_time` service
- 🧩 Generic `chaster.api_request` service for documented API operations
- 🧩 Generic `chaster.lock_action` service for supported lock endpoints
- 📡 Home Assistant events for API responses, lock actions, and messages
- ⚙️ Configurable polling interval and optional features

## Requirements

- Home Assistant with HACS installed
- A Chaster account
- A Chaster developer/API token with the required API access
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

### Manual installation

Copy the `custom_components/chaster` directory into:

```text
/config/custom_components/chaster
```

Then restart Home Assistant and add **Chaster** from **Settings → Devices & services**.

## Authentication

This integration uses a **Chaster developer token** directly. OAuth, browser login, client IDs, client secrets, and OAuth callbacks are not required.

### Get a developer token

1. Open the [Chaster developer area](https://chaster.app/developers).
2. Request API access if you have not already been approved.
3. Open the **Developer interface**.
4. Create or open an application.
5. Select **Tokens** in the left sidebar.
6. Click **Generate a developer token**.
7. Copy the token and enter it when configuring the Home Assistant integration.

**Keep your token private.** Never post it in GitHub issues, forums, Discord, screenshots, or other public locations.

Official Chaster documentation:

- [Getting started](https://docs.chaster.app/api/basics/getting-started/)
- [Developer tokens](https://docs.chaster.app/api/public-api/developer-token/)
- [Public API endpoints](https://docs.chaster.app/api/public-api/endpoints/)
- [API scopes](https://docs.chaster.app/api/reference/scopes/)

## Configuration

After adding the integration, open:

**Settings → Devices & services → Chaster → Configure**

The available options include:

| Option | Description |
| --- | --- |
| **Polling interval** | How often Home Assistant refreshes Chaster data. |
| **Role mode** | Automatically detect the account role or force Wearer, Keyholder, or Both. |
| **Keyholder features** | Enable keyholder-related entities and data. |
| **Shared locks** | Enable shared-lock support when available. |
| **Messaging** | Enable Chaster messaging data/services. |
| **Lock actions** | Enable actions that modify or control locks. |

The polling interval can be configured between **30 and 3600 seconds**.

## Services

### `chaster.add_time`

Adds time to a Chaster lock, subject to the permissions granted by Chaster.

```yaml
action: chaster.add_time
data:
  lock_id: LOCK_ID
  seconds: 3600
```

### `chaster.remove_time`

Removes time from a Chaster lock, subject to the permissions granted by Chaster.

```yaml
action: chaster.remove_time
data:
  lock_id: LOCK_ID
  seconds: 600
```

### `chaster.lock_action`

Calls a supported Chaster lock-action endpoint.

```yaml
action: chaster.lock_action
data:
  lock_id: LOCK_ID
  path: /locks/{lock_id}/...
  method: POST
  body: {}
```

The `{lock_id}` placeholder is replaced automatically.

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

Use the official Chaster API documentation as the source of truth for endpoint paths, request bodies, responses, and permissions.

### `chaster.send_message`

Sends a message using a Chaster conversation endpoint.

```yaml
action: chaster.send_message
data:
  path: /conversations/CONVERSATION_ID
  body:
    # documented Chaster message payload
```

## Home Assistant events

The integration exposes events that can be useful in automations.

### `chaster_api_response`

Fired after a successful generic API request.

Example event data:

```yaml
method: GET
path: /permissions/definitions
result: ...
```

### `chaster_action`

Fired after a lock action or time change.

Example event data:

```yaml
lock_id: LOCK_ID
action: add_time
seconds: 3600
result: ...
```

### `chaster_message`

Fired after sending a message.

Example event data:

```yaml
result: ...
```

## Permissions and safety

Chaster is authoritative for all account and lock permissions.

The integration does **not** attempt to bypass:

- API scopes
- Lock permissions
- Minimum or maximum dates
- Timer restrictions
- History visibility
- Extension permissions
- Safety settings
- Freeze/unfreeze restrictions
- Unlock restrictions

If Chaster rejects an operation, the integration will not override that decision.

Where the API provides permission information, the integration exposes it through the relevant lock entities.

## Existing installations

The integration stores the developer token as `token`.

Existing installations using the developer-token configuration can continue to use their stored token.

If you are upgrading from an older OAuth-based version, remove the old Chaster integration and add it again using a developer token.

## Development

The Home Assistant integration lives in:

```text
custom_components/chaster/
```

The project uses:

- Python
- Home Assistant config entries and config flow
- Home Assistant DataUpdateCoordinator
- HACS
- GitHub Actions

Validation includes:

- Home Assistant **hassfest**
- HACS validation
- Python bytecode compilation

## Repository

Source code and issue tracking are available on GitHub:

https://github.com/jonny5509/Chaster-ha

## Chaster documentation

For API behaviour, supported endpoints, request formats, scopes, and permissions, always refer to the official Chaster documentation:

https://docs.chaster.app/api/public-api/endpoints/

## License

MIT License. See [LICENSE](LICENSE).
