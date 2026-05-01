DOMAIN = "opnsense_kea_syslog"

CONF_BIND_HOST = "bind_host"
CONF_PORT = "port"
CONF_ALLOWED_IPS = "allowed_ips"
CONF_MONITORED_MACS = "monitored_macs"
CONF_ENABLE_ALLOC = "enable_alloc"
CONF_ENABLE_RENEW = "enable_renew"
CONF_COOLDOWN_SECONDS = "cooldown_seconds"
CONF_LOG_ALL_LINES = "log_all_lines"

DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_PORT = 10514
DEFAULT_ALLOWED_IPS: list[str] = []
DEFAULT_MONITORED_MACS: list[str] = []
DEFAULT_ENABLE_ALLOC = True
DEFAULT_ENABLE_RENEW = True
DEFAULT_COOLDOWN_SECONDS = 300
DEFAULT_LOG_ALL_LINES = False

EVENT_DEVICE_JOINED_NETWORK = "device_joined_network"

# Basic protection against overly large syslog lines.
DEFAULT_MAX_LINE_BYTES = 8192

