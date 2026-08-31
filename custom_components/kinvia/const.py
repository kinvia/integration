"""Constants for the Kinvia integration."""

DOMAIN = "kinvia"

CONF_URL = "url"
CONF_WEBHOOK_SECRET = "webhook_secret"
CONF_MONITORED_DOMAINS = "monitored_domains"
CONF_EXCLUDED_ENTITIES = "excluded_entities"
CONF_BATTERY_THRESHOLD = "battery_threshold"
CONF_STARTUP_GRACE_MINUTES = "startup_grace_minutes"
CONF_STARTUP_BASELINE = "startup_baseline"

DEFAULT_MONITORED_DOMAINS = [
    "light",
    "switch",
    "binary_sensor",
    "sensor",
    "cover",
    "climate",
    "lock",
    "fan",
    "camera",
    "media_player",
    "device_tracker",
    "vacuum",
    "valve",
    "water_heater",
    "humidifier",
    "number",
    "select",
    "button",
]

DEFAULT_BATTERY_THRESHOLD = 15
DEFAULT_STARTUP_GRACE_MINUTES = 10
DEFAULT_STARTUP_BASELINE = True

WEBHOOK_PATH = "/api/v1/webhooks/incidents"
SERVER_HEALTH_PATH = "/health"
WEBHOOK_HEALTH_PATH = "/api/v1/webhooks/health"

EVENT_STATE_CHANGED = "state_changed"
EVENT_REPAIRS_UPDATED = "repairs_issue_registry_updated"

REPAIR_RECONCILE_INTERVAL_SECONDS = 900

INVALID_STATES = frozenset({"unavailable", "unknown", "none", ""})
