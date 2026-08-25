"""Pure-Python SNMPv2c client (RFC 1157 / RFC 3416).

Implements BER encoding/decoding for SNMP GET requests with no third-party
dependencies beyond the standard library. Supports any UDP port and the
OIDs used for device identification.
"""

from __future__ import annotations

import random
import socket
from dataclasses import dataclass

SNMP_PORT = 161
DEFAULT_TIMEOUT = 1.5

OIDS = {
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
}


# ── BER encoding ─────────────────────────────────────────────────────────────

def _encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    body = bytearray()
    while length > 0:
        body.insert(0, length & 0xFF)
        length >>= 8
    return bytes([0x80 | len(body)]) + bytes(body)


def _encode_integer(value: int) -> bytes:
    body = bytearray()
    if value >= 0:
        while value >= 0x80:
            body.insert(0, value & 0xFF)
            value >>= 8
        body.insert(0, value)
    else:
        # Negative integers (rare in this client) encoded two's complement.
        body = bytearray((value >> (i * 8)) & 0xFF for i in reversed(range(4)))
    return b"\x02" + _encode_length(len(body)) + bytes(body)


def _encode_octet_string(text: str) -> bytes:
    payload = text.encode("utf-8")
    return b"\x04" + _encode_length(len(payload)) + payload


def _encode_oid(oid: str) -> bytes:
    parts = [int(p) for p in oid.split(".")]
    payload = bytearray([parts[0] * 40 + parts[1]])
    for part in parts[2:]:
        sub = []
        while part >= 128:
            sub.insert(0, part % 128)
            part >>= 7
        sub.insert(0, part)
        for i, b in enumerate(sub):
            payload.append(b | 0x80 if i < len(sub) - 1 else b)
    return b"\x06" + _encode_length(len(payload)) + bytes(payload)


def _encode_varbind(oid: str) -> bytes:
    oid_bytes = _encode_oid(oid)
    body = oid_bytes + b"\x05\x00"  # NULL value (GET request)
    return b"\x30" + _encode_length(len(body)) + body


def build_get_request(oid_list, community: str, request_id: int) -> bytes:
    version = _encode_integer(1)  # SNMPv2c
    comm = _encode_octet_string(community)
    varbinds = b"".join(_encode_varbind(oid) for oid in oid_list)
    vb_seq = b"\x30" + _encode_length(len(varbinds)) + varbinds
    pdu_body = _encode_integer(request_id) + _encode_integer(0) + _encode_integer(0) + vb_seq
    pdu = b"\xa0" + _encode_length(len(pdu_body)) + pdu_body  # GetRequest-PDU
    msg_body = version + comm + pdu
    return b"\x30" + _encode_length(len(msg_body)) + msg_body


def build_getbulk_request(non_repeaters: int, max_repetitions: int, oid_list,
                          community: str, request_id: int) -> bytes:
    version = _encode_integer(1)  # SNMPv2c
    comm = _encode_octet_string(community)
    varbinds = b"".join(_encode_varbind(oid) for oid in oid_list)
    vb_seq = b"\x30" + _encode_length(len(varbinds)) + varbinds
    pdu_body = (_encode_integer(request_id) + _encode_integer(non_repeaters)
                + _encode_integer(max_repetitions) + vb_seq)
    pdu = b"\xa5" + _encode_length(len(pdu_body)) + pdu_body  # GetBulkRequest-PDU
    msg_body = version + comm + pdu
    return b"\x30" + _encode_length(len(msg_body)) + msg_body


# ── BER decoding ─────────────────────────────────────────────────────────────

@dataclass
class _TLV:
    type: int
    length: int
    value_start: int
    value_end: int


def _read_tlv(buf: bytes, offset: int) -> _TLV:
    if offset + 2 > len(buf):
        raise ValueError("Truncated TLV")
    tag = buf[offset]
    length = buf[offset + 1]
    len_bytes = 0
    if length & 0x80:
        len_bytes = length & 0x7F
        if offset + 1 + len_bytes > len(buf):
            raise ValueError("Truncated length")
        length = 0
        for i in range(len_bytes):
            length = length * 256 + buf[offset + 2 + i]
    value_start = offset + 2 + len_bytes
    if value_start + length > len(buf):
        raise ValueError("Truncated value")
    return _TLV(tag, length, value_start, value_start + length)


def _parse_oid(buf: bytes, start: int, end: int) -> str:
    parts: list[int] = []
    first = True
    value = 0
    i = start
    while i < end:
        byte = buf[i]
        value = value * 128 + (byte & 0x7F)
        if not (byte & 0x80):
            if first:
                if value < 40:
                    parts.extend((0, value))
                elif value < 80:
                    parts.extend((1, value - 40))
                else:
                    parts.extend((2, value - 80))
                first = False
            else:
                parts.append(value)
            value = 0
        i += 1
    return ".".join(str(p) for p in parts)


def _to_str(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return "" if value is None else str(value)


def _parse_value(tlv: _TLV, buf: bytes):
    raw = buf[tlv.value_start:tlv.value_end]
    if tlv.type in (0x02, 0x80, 0x81):  # INTEGER / contexts
        value = 0
        for byte in raw:
            value = value * 256 + byte
        return value
    if tlv.type == 0x04:  # OCTET STRING (raw bytes; decode at call sites)
        return raw
    if tlv.type == 0x06:  # OBJECT IDENTIFIER
        return "." + _parse_oid(buf, tlv.value_start, tlv.value_end)
    if tlv.type in (0x41, 0x42, 0x43, 0x46):  # Counter32 / Gauge32 / TimeTicks / Counter64
        value = 0
        for byte in raw:
            value = value * 256 + byte
        return value
    return None


def parse_response_checked(buf: bytes) -> tuple[dict, int]:
    """Decode an SNMP response into ({oid_string: value}, error_status).

    error_status is the PDU error-status field (0 == noError). Agents that
    reject a GET (e.g. an unknown community) respond with a non-zero
    error-status and NULL varbinds instead of staying silent, so callers must
    check it or they will mistake an error for a successful identification.
    """
    msg = _read_tlv(buf, 0)
    offset = msg.value_start
    offset = _skip_tlv(buf, offset)   # version
    offset = _skip_tlv(buf, offset)   # community
    pdu = _read_tlv(buf, offset)
    offset = pdu.value_start
    offset = _skip_tlv(buf, offset)   # request-id
    status_tlv = _read_tlv(buf, offset)
    error_status = int(_parse_value(status_tlv, buf) or 0)
    offset = status_tlv.value_end
    offset = _skip_tlv(buf, offset)   # error-index
    vb_seq = _read_tlv(buf, offset)
    offset = vb_seq.value_start
    result: dict = {}
    while offset < vb_seq.value_end:
        bind = _read_tlv(buf, offset)
        inner = bind.value_start
        oid_tlv = _read_tlv(buf, inner)
        oid = _parse_oid(buf, oid_tlv.value_start, oid_tlv.value_end)
        inner = oid_tlv.value_end
        val_tlv = _read_tlv(buf, inner)
        result[oid] = _parse_value(val_tlv, buf)
        offset = bind.value_end
    return result, error_status


def parse_response(buf: bytes) -> dict:
    """Decode an SNMP response into {oid_string: value} (error-status ignored)."""
    return parse_response_checked(buf)[0]


def _skip_tlv(buf: bytes, offset: int) -> int:
    return _read_tlv(buf, offset).value_end


# ── Transport ────────────────────────────────────────────────────────────────

def send_get_request(host: str, oid_list, community: str, timeout: float = DEFAULT_TIMEOUT, port: int = SNMP_PORT):
    """Send one SNMP GET and return the decoded response dict or raise."""
    request_id = random.getrandbits(31)
    packet = build_get_request(oid_list, community, request_id)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(packet, (host, port))
        data, _ = sock.recvfrom(65535)
        result, error_status = parse_response_checked(data)
        if error_status:
            raise ValueError(f"SNMP error-status {error_status}")
        return result
    finally:
        sock.close()


def snmp_walk(host: str, subtree_oid: str, community: str,
              max_repetitions: int = 20, timeout: float = DEFAULT_TIMEOUT,
              port: int = SNMP_PORT, max_oids: int = 1024) -> dict:
    """Walk a subtree via GETBULK, returning {oid: value}; {} on failure."""
    subtree_oid = subtree_oid.rstrip(".")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    results: dict = {}
    current_oid = subtree_oid
    oid_count = 0
    try:
        for _ in range(max_oids // max_repetitions + 1):
            request_id = random.getrandbits(31)
            packet = build_getbulk_request(0, max_repetitions, [current_oid], community, request_id)
            sock.sendto(packet, (host, port))
            data, _ = sock.recvfrom(65535)
            resp, error_status = parse_response_checked(data)
            if error_status:
                return results
            if not resp:
                return results
            for oid_key, val in resp.items():
                if not oid_key.startswith(subtree_oid):
                    return results
                results[oid_key] = val
                current_oid = oid_key
                oid_count += 1
            if len(resp) < max_repetitions:
                break
            if oid_count >= max_oids:
                break
        return results
    except (socket.timeout, OSError, ValueError):
        return {}
    finally:
        sock.close()


# ── IF-MIB table walk (v2c) ──────────────────────────────────────────────────

IF_NUMBER = "1.3.6.1.2.1.2.1"
IF_TABLE = "1.3.6.1.2.1.2.2.1"
IF_XTABLE = "1.3.6.1.2.1.31.1.1.1"

_IF_COL_DESCR = 2
_IF_COL_TYPE = 3
_IF_COL_SPEED = 5
_IF_COL_PHYS_ADDR = 6
_IF_COL_ADMIN = 7
_IF_COL_OPER = 8
_IFX_COL_NAME = 1
_IFX_COL_HCIN = 6
_IFX_COL_HCOUT = 10
_IFX_COL_HIGH_SPEED = 15
_IF_COL_IF_ALIAS = 18

_IF_TYPE_MAP = {
    1: "other", 6: "ethernet", 24: "softwareLoopback", 53: "propVirtual",
    135: "l2vlan", 136: "l3ipvlan", 161: "ieee8023adLag", 209: "bridge",
}


def _if_parts_from_oid(oid: str, subtree: str) -> tuple[str, str]:
    prefix = subtree + "."
    if oid.startswith(prefix):
        parts = oid[len(prefix):].split(".", 2)
        if len(parts) >= 2:
            return parts[0], parts[1]
    return "", ""


def walk_if_table(host: str, communities: list[str], port: int = SNMP_PORT,
                  timeout: float = DEFAULT_TIMEOUT, max_oids: int = 2048) -> list[dict[str, str]]:
    """Walk ifTable + ifXTable over SNMPv2c; [] on total failure.

    Mirrors the SNMPv3 walk_if_table but uses GETBULK via the v2c client so
    interface discovery works for devices reachable with a v2c community.
    """
    count_result = None
    community_used = ""
    for community in communities:
        try:
            result = send_get_request(host, [IF_NUMBER + ".0"], community, timeout, port)
        except (socket.timeout, OSError, ValueError):
            continue
        if result and IF_NUMBER + ".0" in result:
            count_result = result
            community_used = community
            break
    if count_result is None:
        return []
    try:
        if_count = int(count_result.get(IF_NUMBER + ".0", 0) or 0)
    except (TypeError, ValueError):
        if_count = 0
    if if_count == 0:
        return []

    if_raw = snmp_walk(host, IF_TABLE + ".", community_used, port=port,
                       timeout=timeout, max_oids=max_oids)
    ifx_raw = snmp_walk(host, IF_XTABLE + ".", community_used, port=port,
                        timeout=timeout, max_oids=max_oids)

    interfaces: dict[str, dict[str, str]] = {}
    for oid, val in if_raw.items():
        col, idx = _if_parts_from_oid(oid, IF_TABLE)
        if not col or not idx:
            continue
        col = int(col)
        if idx not in interfaces:
            interfaces[idx] = {"ifIndex": idx}
        entry = interfaces[idx]
        if col == _IF_COL_DESCR:
            entry["ifDescr"] = _to_str(val)
        elif col == _IF_COL_TYPE:
            entry["ifType"] = _IF_TYPE_MAP.get(int(val), _to_str(val))
        elif col == _IF_COL_SPEED:
            entry["ifSpeed"] = str(int(val)) if val is not None else ""
        elif col == _IF_COL_PHYS_ADDR:
            entry["ifPhysAddress"] = ":".join(f"{b:02x}" for b in val) if isinstance(val, bytes) else ""
        elif col == _IF_COL_ADMIN:
            entry["ifAdminStatus"] = {1: "up", 2: "down", 3: "testing"}.get(int(val), _to_str(val))
        elif col == _IF_COL_OPER:
            entry["ifOperStatus"] = {1: "up", 2: "down", 3: "testing"}.get(int(val), _to_str(val))

    for oid, val in ifx_raw.items():
        col, idx = _if_parts_from_oid(oid, IF_XTABLE)
        if not col or not idx or idx not in interfaces:
            continue
        col = int(col)
        entry = interfaces[idx]
        if col == _IFX_COL_NAME:
            entry["ifName"] = _to_str(val)
        elif col == _IFX_COL_HCIN:
            entry["ifHCInOctets"] = str(int(val)) if val is not None else "0"
        elif col == _IFX_COL_HCOUT:
            entry["ifHCOutOctets"] = str(int(val)) if val is not None else "0"
        elif col == _IFX_COL_HIGH_SPEED:
            entry["ifHighSpeed"] = str(int(val)) if val is not None else ""
        elif col == _IF_COL_IF_ALIAS:
            entry["ifAlias"] = _to_str(val)

    return [interfaces[i] for i in sorted(interfaces, key=lambda x: int(x))]


def snmp_poll(host: str, community_list, timeout: float = DEFAULT_TIMEOUT, port: int = SNMP_PORT):
    """Try each community in turn; return the first non-empty result dict."""
    communities = community_list if isinstance(community_list, list) else ["public"]
    oid_list = [OIDS["sysDescr"], OIDS["sysObjectID"], OIDS["sysName"]]
    for community in communities:
        try:
            result = send_get_request(host, oid_list, community, timeout, port)
        except (socket.timeout, OSError, ValueError):
            continue
        if result and len(result) > 0:
            sys_name = _to_str(result.get(OIDS["sysName"], ""))
            sys_descr = _to_str(result.get(OIDS["sysDescr"], ""))
            sys_oid = _to_str(result.get(OIDS["sysObjectID"], ""))
            # A well-formed but value-less response (error PDU / varbind
            # exceptions) must not count as a successful identification.
            if not (sys_name or sys_descr or sys_oid):
                continue
            return {
                "sysName": sys_name,
                "sysDescr": sys_descr,
                "sysObjectID": sys_oid,
                "community": community,
            }
    return None
