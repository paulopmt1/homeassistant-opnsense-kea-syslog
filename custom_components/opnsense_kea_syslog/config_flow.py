from __future__ import annotations

import json
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ALLOWED_IPS,
    CONF_BIND_HOST,
    CONF_COOLDOWN_SECONDS,
    CONF_ENABLE_ALLOC,
    CONF_ENABLE_RENEW,
    CONF_LOG_ALL_LINES,
    CONF_MONITORED_MACS,
    CONF_PORT,
    DEFAULT_ALLOWED_IPS,
    DEFAULT_BIND_HOST,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_ENABLE_ALLOC,
    DEFAULT_ENABLE_RENEW,
    DEFAULT_LOG_ALL_LINES,
    DEFAULT_MONITORED_MACS,
    DEFAULT_PORT,
    DOMAIN,
)


def _string_list_default(value: Any) -> str:
    """Convert stored list/str to a user-friendly multiline default."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(x) for x in value if str(x).strip())
    return str(value)


def _monitored_macs_default(value: Any) -> str:
    """Convert stored monitored_macs to a JSON editor-friendly default."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value

    # Already in the new shape (list[dict]) or a list of strings (legacy).
    if isinstance(value, list):
        items: list[dict[str, str]] = []
        for x in value:
            if isinstance(x, dict):
                name = str(x.get("name", "")).strip()
                mac = str(x.get("mac", "")).strip()
                if mac:
                    items.append({"name": name, "mac": mac})
                continue
            s = str(x).strip()
            if s:
                items.append({"name": "", "mac": s})
        return json.dumps(items, indent=2, ensure_ascii=False)

    return str(value)


def _parse_string_list(value: Any) -> list[str]:
    """Parse multiline/comma-separated input into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if not isinstance(value, str):
        return [str(value).strip()] if str(value).strip() else []

    raw = value.replace(",", "\n")
    items = [s.strip() for s in raw.splitlines()]
    return [s for s in items if s]


def _parse_monitored_macs(value: Any) -> list[dict[str, str]]:
    """Parse monitored_macs as JSON (preferred) or legacy newline list."""
    if value is None:
        return []
    if isinstance(value, list):
        out: list[dict[str, str]] = []
        for x in value:
            if isinstance(x, dict):
                name = str(x.get("name", "")).strip()
                mac = str(x.get("mac", "")).strip()
                if mac:
                    out.append({"name": name, "mac": mac})
                continue
            s = str(x).strip()
            if s:
                out.append({"name": "", "mac": s})
        return out

    if not isinstance(value, str):
        s = str(value).strip()
        return [{"name": "", "mac": s}] if s else []

    s = value.strip()
    if not s:
        return []

    # Preferred: JSON array of {name, mac}
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            out2: list[dict[str, str]] = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                mac = str(item.get("mac", "")).strip()
                if mac:
                    out2.append({"name": name, "mac": mac})
            return out2
    except json.JSONDecodeError:
        # Fallback to legacy format below.
        pass

    # Legacy: one MAC per line / comma-separated
    return [{"name": "", "mac": mac} for mac in _parse_string_list(s)]


def _schema_with_defaults(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_BIND_HOST, default=defaults.get(CONF_BIND_HOST, DEFAULT_BIND_HOST)): str,
            vol.Optional(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.Coerce(int),
            vol.Optional(
                CONF_ALLOWED_IPS,
                default=_string_list_default(defaults.get(CONF_ALLOWED_IPS, DEFAULT_ALLOWED_IPS)),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Optional(
                CONF_MONITORED_MACS,
                default=_monitored_macs_default(defaults.get(CONF_MONITORED_MACS, DEFAULT_MONITORED_MACS)),
            ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Optional(
                CONF_ENABLE_ALLOC,
                default=defaults.get(CONF_ENABLE_ALLOC, DEFAULT_ENABLE_ALLOC),
            ): bool,
            vol.Optional(
                CONF_ENABLE_RENEW,
                default=defaults.get(CONF_ENABLE_RENEW, DEFAULT_ENABLE_RENEW),
            ): bool,
            vol.Optional(
                CONF_COOLDOWN_SECONDS,
                default=defaults.get(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS),
            ): vol.Coerce(int),
            vol.Optional(
                CONF_LOG_ALL_LINES,
                default=defaults.get(CONF_LOG_ALL_LINES, DEFAULT_LOG_ALL_LINES),
            ): bool,
        }
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = dict(user_input)
            user_input[CONF_ALLOWED_IPS] = _parse_string_list(user_input.get(CONF_ALLOWED_IPS))
            user_input[CONF_MONITORED_MACS] = _parse_monitored_macs(user_input.get(CONF_MONITORED_MACS))

            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            cooldown = user_input.get(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS)
            if not (1 <= int(port) <= 65535):
                errors[CONF_PORT] = "invalid_port"
            elif int(cooldown) < 0:
                errors[CONF_COOLDOWN_SECONDS] = "invalid_cooldown"
            else:
                return self.async_create_entry(title="OPNsense Kea Syslog", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_schema_with_defaults({}),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = dict(user_input)
            user_input[CONF_ALLOWED_IPS] = _parse_string_list(user_input.get(CONF_ALLOWED_IPS))
            user_input[CONF_MONITORED_MACS] = _parse_monitored_macs(user_input.get(CONF_MONITORED_MACS))

            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            cooldown = user_input.get(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS)
            if not (1 <= int(port) <= 65535):
                errors[CONF_PORT] = "invalid_port"
            elif int(cooldown) < 0:
                errors[CONF_COOLDOWN_SECONDS] = "invalid_cooldown"
            else:
                return self.async_create_entry(title="", data=user_input)

        defaults: dict[str, Any] = {**self._config_entry.data, **self._config_entry.options}

        return self.async_show_form(
            step_id="init",
            data_schema=_schema_with_defaults(defaults),
            errors=errors,
        )

