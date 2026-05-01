from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class KeaEvent:
    event_type: str  # DHCP4_LEASE_ALLOC | DHCP4_LEASE_RENEW
    mac: str         # AA:BB:CC:DD:EE:FF
    ip: str | None   # 192.168.1.101


_EVENT_RE = re.compile(r"\b(DHCP4_LEASE_ALLOC|DHCP4_LEASE_RENEW)\b")
_CID_RE = re.compile(r"\bcid=\[([^\]]+)\]")
_HW_RE = re.compile(r"\bhwtype=\d+\s+([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\b")
_LEASE_IP_RE = re.compile(r"\blease\s+(\d{1,3}(?:\.\d{1,3}){3})\b")


def _normalize_mac(value: str) -> str | None:
    mac = value.strip().lower()
    if not mac:
        return None

    if mac.startswith("01:") and len(mac.split(":")) == 7:
        mac = ":".join(mac.split(":")[1:])

    mac = mac.replace("-", ":")
    parts = mac.split(":")
    if len(parts) != 6:
        return None
    try:
        parts = [f"{int(p, 16):02x}" for p in parts]
    except ValueError:
        return None
    return ":".join(parts)


def parse_kea_log_line(line: str) -> KeaEvent | None:
    m_event = _EVENT_RE.search(line)
    if not m_event:
        return None

    event_type = m_event.group(1)

    mac: str | None = None
    m_cid = _CID_RE.search(line)
    if m_cid:
        mac = _normalize_mac(m_cid.group(1))

    if not mac:
        m_hw = _HW_RE.search(line)
        if m_hw:
            mac = _normalize_mac(m_hw.group(1))

    if not mac:
        return None

    m_ip = _LEASE_IP_RE.search(line)
    ip = m_ip.group(1) if m_ip else None

    return KeaEvent(event_type=event_type, mac=mac, ip=ip)

