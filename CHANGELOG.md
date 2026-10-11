# Changelog

## [2.3.7] - 2026-10-11

### Fixed
- Fixed the Test notification button being unavailable when lock actions were disabled or no lock was present.

## [2.3.6] - 2026-10-11

### Added
- Added a pressable `Test notification` button entity that sends a test message through the configured notification service.

## [2.3.5] - 2026-10-11

### Added
- Added the `chaster.test_notification` service to verify the configured Home Assistant notification target, with an optional custom test message.
- Test notifications can be sent even when automatic Chaster notifications are disabled.

## [2.3.4] - 2026-10-11

### Fixed
- Fixed options-flow form serialization on Home Assistant versions where `voluptuous.Match` cannot be serialized by the config-flow API.
- Validate notification service names when submitting options and fall back to `notify.notify` for invalid values.

## [2.3.3] - 2026-10-11

### Fixed
- Hardened configuration startup by normalizing invalid polling intervals and role settings.
- Improved handling of invalid and extreme API timer values.
- Escaped dynamic dashboard-card content to reduce unsafe HTML rendering.
- Improved lock timer parsing and expiration validation.
- Used the authenticated Chaster username for new integration entries.
- Added a safe fallback for malformed saved notification-service settings.
- Corrected negative millisecond Unix timestamp parsing in calendar events.
- Added and expanded regression tests for API, coordinator settings, and calendar timestamps.

## [2.3.2]
- Fixed Home Assistant config-flow compatibility and improved API safety.
