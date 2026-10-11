from __future__ import annotations

DOMAIN = "chaster"
API_BASE = "https://api.chaster.app"
CONF_TOKEN = "token"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ROLE_MODE = "role_mode"
CONF_ENABLE_MESSAGING = "enable_messaging"
CONF_ENABLE_SHARED_LOCKS = "enable_shared_locks"
CONF_ENABLE_KEYHOLDER = "enable_keyholder"
CONF_ENABLE_LOCK_ACTIONS = "enable_lock_actions"
CONF_ENABLE_NOTIFICATIONS = "enable_notifications"
CONF_NOTIFICATION_SERVICE = "notification_service"
CONF_NOTIFY_DAILY = "notify_daily_congratulations"
CONF_NOTIFY_COMPLETION = "notify_lock_completion"
CONF_NOTIFY_WEARER = "notify_wearer_locks"
CONF_NOTIFY_KEYHOLDER = "notify_keyholder_locks"
DEFAULT_NOTIFICATION_SERVICE = "notify.notify"
DEFAULT_SCAN_INTERVAL = 60
ROLE_AUTO = "auto"
ROLE_WEARER = "wearer"
ROLE_KEYHOLDER = "keyholder"
ROLE_BOTH = "both"
PLATFORMS = ["sensor", "button", "binary_sensor", "calendar"]
ATTR_LOCK_ID = "lock_id"

CONF_NOTIFY_HA_DAILY = "notify_ha_daily"
CONF_NOTIFY_HA_COMPLETION = "notify_ha_completion"
