from __future__ import annotations

import asyncio
import ipaddress
import logging
from dataclasses import dataclass
from time import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

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
    DEFAULT_MAX_LINE_BYTES,
    DEFAULT_MONITORED_MACS,
    DEFAULT_PORT,
    DOMAIN,
    EVENT_DEVICE_JOINED_NETWORK,
)
from .parser import KeaEvent, parse_kea_log_line

_LOGGER = logging.getLogger(__name__)

DATA_SERVER = "server"
DATA_SERVER_TASKS = "tasks"
DATA_LAST_SEEN = "last_seen"


@dataclass(frozen=True)
class RuntimeConfig:
    bind_host: str
    port: int
    allowed_networks: tuple[ipaddress._BaseNetwork, ...]
    monitored_macs: frozenset[str]
    enable_alloc: bool
    enable_renew: bool
    cooldown_seconds: int
    log_all_lines: bool
    max_line_bytes: int


def _normalize_mac(value: str) -> str | None:
    mac = value.strip().lower()
    if not mac:
        return None
    mac = mac.replace("-", ":")
    parts = mac.split(":")
    if len(parts) != 6:
        return None
    try:
        parts = [f"{int(p, 16):02x}" for p in parts]
    except ValueError:
        return None
    return ":".join(parts)


def _compile_allowed_networks(values: list[str]) -> tuple[ipaddress._BaseNetwork, ...]:
    networks: list[ipaddress._BaseNetwork] = []
    for raw in values:
        s = raw.strip()
        if not s:
            continue
        try:
            if "/" in s:
                networks.append(ipaddress.ip_network(s, strict=False))
            else:
                ip = ipaddress.ip_address(s)
                networks.append(ipaddress.ip_network(f"{ip}/{ip.max_prefixlen}", strict=False))
        except ValueError:
            _LOGGER.warning("Ignoring invalid allowed IP/CIDR: %s", raw)
    return tuple(networks)


def _is_ip_allowed(remote_ip: str, allowed: tuple[ipaddress._BaseNetwork, ...]) -> bool:
    if not allowed:
        return True
    try:
        ip = ipaddress.ip_address(remote_ip)
    except ValueError:
        return False
    return any(ip in net for net in allowed)


def _build_runtime_config(entry: ConfigEntry) -> RuntimeConfig:
    cfg: dict[str, Any] = {**entry.data, **entry.options}

    bind_host = str(cfg.get(CONF_BIND_HOST, DEFAULT_BIND_HOST))
    port = int(cfg.get(CONF_PORT, DEFAULT_PORT))
    allowed_val = cfg.get(CONF_ALLOWED_IPS, DEFAULT_ALLOWED_IPS)
    if isinstance(allowed_val, str):
        allowed_ips = [s.strip() for s in allowed_val.replace(",", "\n").splitlines() if s.strip()]
    else:
        allowed_ips = list(allowed_val or [])

    monitored_val = cfg.get(CONF_MONITORED_MACS, DEFAULT_MONITORED_MACS)
    if isinstance(monitored_val, str):
        monitored_raw = [s.strip() for s in monitored_val.replace(",", "\n").splitlines() if s.strip()]
    else:
        monitored_raw = list(monitored_val or [])

    monitored: set[str] = set()
    for m in monitored_raw:
        nm = _normalize_mac(str(m))
        if nm:
            monitored.add(nm)
        else:
            _LOGGER.warning("Ignoring invalid monitored MAC: %s", m)

    return RuntimeConfig(
        bind_host=bind_host,
        port=port,
        allowed_networks=_compile_allowed_networks([str(x) for x in allowed_ips]),
        monitored_macs=frozenset(monitored),
        enable_alloc=bool(cfg.get(CONF_ENABLE_ALLOC, DEFAULT_ENABLE_ALLOC)),
        enable_renew=bool(cfg.get(CONF_ENABLE_RENEW, DEFAULT_ENABLE_RENEW)),
        cooldown_seconds=int(cfg.get(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS)),
        log_all_lines=bool(cfg.get(CONF_LOG_ALL_LINES, DEFAULT_LOG_ALL_LINES)),
        max_line_bytes=DEFAULT_MAX_LINE_BYTES,
    )


async def async_start_server(hass: HomeAssistant, entry: ConfigEntry) -> None:
    runtime = _build_runtime_config(entry)
    state = hass.data[DOMAIN][entry.entry_id]
    state.setdefault(DATA_SERVER_TASKS, set())
    state.setdefault(DATA_LAST_SEEN, {})

    async def client_connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        remote_ip = peer[0] if peer and len(peer) >= 1 else None

        if not remote_ip or not _is_ip_allowed(remote_ip, runtime.allowed_networks):
            _LOGGER.warning("Rejected syslog TCP connection from %s", remote_ip)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            return

        _LOGGER.debug("Accepted syslog TCP connection from %s", remote_ip)
        task = hass.async_create_task(
            _handle_client(hass, entry, runtime, remote_ip, reader, writer)
        )
        state[DATA_SERVER_TASKS].add(task)
        task.add_done_callback(lambda t: state[DATA_SERVER_TASKS].discard(t))

    server = await asyncio.start_server(client_connected, host=runtime.bind_host, port=runtime.port)
    state[DATA_SERVER] = server

    sockets = server.sockets or []
    binds = ", ".join(f"{s.getsockname()[0]}:{s.getsockname()[1]}" for s in sockets)
    _LOGGER.info("OPNsense Kea syslog TCP server listening on %s", binds or f"{runtime.bind_host}:{runtime.port}")


async def async_stop_server(hass: HomeAssistant, entry: ConfigEntry) -> None:
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not state:
        return

    server: asyncio.AbstractServer | None = state.get(DATA_SERVER)
    if server is not None:
        server.close()
        await server.wait_closed()
        state[DATA_SERVER] = None

    tasks: set[asyncio.Task] = state.get(DATA_SERVER_TASKS, set())
    for t in list(tasks):
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        tasks.clear()


async def async_restart_server(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_stop_server(hass, entry)
    await async_start_server(hass, entry)


async def _handle_client(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime: RuntimeConfig,
    remote_ip: str,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    state = hass.data[DOMAIN][entry.entry_id]
    last_seen: dict[str, float] = state[DATA_LAST_SEEN]

    try:
        while not reader.at_eof():
            raw = await reader.readline()
            if not raw:
                break
            if len(raw) > runtime.max_line_bytes:
                raw = raw[: runtime.max_line_bytes]

            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            if runtime.log_all_lines:
                _LOGGER.info("Syslog line from %s: %s", remote_ip, line)

            event: KeaEvent | None = parse_kea_log_line(line)
            if event is not None:
                _LOGGER.debug(
                    "Parsed Kea event from %s: event_type=%s mac=%s ip=%s",
                    remote_ip,
                    event.event_type,
                    event.mac,
                    event.ip,
                )
            if event is None:
                continue

            if event.event_type == "DHCP4_LEASE_ALLOC" and not runtime.enable_alloc:
                continue
            if event.event_type == "DHCP4_LEASE_RENEW" and not runtime.enable_renew:
                continue

            if event.mac not in runtime.monitored_macs:
                continue

            now = time()
            prev = last_seen.get(event.mac, 0.0)
            if runtime.cooldown_seconds > 0 and (now - prev) < runtime.cooldown_seconds:
                continue
            last_seen[event.mac] = now

            payload = {
                "mac": event.mac,
                "event_type": event.event_type,
                "ip": event.ip,
                "remote_ip": remote_ip,
                "raw": line,
                "ts": dt_util.utcnow().isoformat(),
            }
            _LOGGER.debug(
                "Firing %s: mac=%s event_type=%s ip=%s remote_ip=%s",
                EVENT_DEVICE_JOINED_NETWORK,
                payload.get("mac"),
                payload.get("event_type"),
                payload.get("ip"),
                payload.get("remote_ip"),
            )
            hass.bus.async_fire(EVENT_DEVICE_JOINED_NETWORK, payload)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _LOGGER.exception("Error handling syslog client %s: %s", remote_ip, exc)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

