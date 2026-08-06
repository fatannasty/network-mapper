"""Tests for the pure-Python SNMPv2c client against a mock UDP agent."""

import socket
import threading

import pytest

import snmp


# ── Mock SNMP agent ──────────────────────────────────────────────────────────

def _encode_len(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    body = bytearray()
    while length > 0:
        body.insert(0, length & 0xFF)
        length >>= 8
    return bytes([0x80 | len(body)]) + bytes(body)


def _encode_oid(oid: str) -> bytes:
    parts = [int(p) for p in oid.lstrip(".").split(".")]
    payload = bytearray([parts[0] * 40 + parts[1]])
    for part in parts[2:]:
        sub = []
        while part >= 128:
            sub.insert(0, part % 128)
            part >>= 7
        sub.insert(0, part)
        for i, b in enumerate(sub):
            payload.append(b | 0x80 if i < len(sub) - 1 else b)
    return b"\x06" + _encode_len(len(payload)) + bytes(payload)


def _encode_str(value: str) -> bytes:
    payload = value.encode()
    return b"\x04" + _encode_len(len(payload)) + payload


def _build_response(request_id: int, community: str) -> bytes:
    values = [
        ("1.3.6.1.2.1.1.1.0", _encode_str("Cisco IOS Software, C9300L Software (C9300L-24P-4G), Version 17.3.3")),
        ("1.3.6.1.2.1.1.2.0", _encode_oid(".1.3.6.1.4.1.9.1.2345")),
        ("1.3.6.1.2.1.1.5.0", _encode_str("core-sw1")),
    ]
    varbinds = b""
    for oid, value in values:
        body = _encode_oid(oid) + value
        varbinds += b"\x30" + _encode_len(len(body)) + body
    vb_seq = b"\x30" + _encode_len(len(varbinds)) + varbinds
    body = snmp._encode_integer(request_id) + snmp._encode_integer(0) + snmp._encode_integer(0) + vb_seq
    pdu = b"\xa2" + _encode_len(len(body)) + body  # GetResponse-PDU
    msg = snmp._encode_integer(1) + _encode_str(community) + pdu
    return b"\x30" + _encode_len(len(msg)) + msg


class MockAgent:
    """UDP SNMP agent that answers GETs for the 'public' community."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        self.sock.settimeout(0.2)
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                # Reuse the request decoder to find request-id + community.
                parsed = snmp.parse_response(data)
                # Rebuild request to extract fields reliably:
                msg = snmp._read_tlv(data, 0)
                off = msg.value_start
                off = snmp._skip_tlv(data, off)  # version
                comm = snmp._read_tlv(data, off)
                community = data[comm.value_start:comm.value_end].decode()
                off = comm.value_end
                pdu = snmp._read_tlv(data, off)
                off = pdu.value_start
                req_id_tlv = snmp._read_tlv(data, off)
                req_id = int.from_bytes(data[req_id_tlv.value_start:req_id_tlv.value_end], "big")
                if community != "public":
                    continue
                response = _build_response(req_id, community)
                self.sock.sendto(response, addr)
            except (ValueError, OSError):
                continue

    def close(self):
        self.running = False
        self.sock.close()


@pytest.fixture
def agent():
    mock = MockAgent()
    yield mock
    mock.close()


class ErrorAgent:
    """UDP SNMP agent that answers every GET with an error PDU.

    Real agents do this when the community is wrong (e.g. error-status=2
    noSuchName with NULL varbinds) instead of staying silent.
    """

    def __init__(self, status: int = 2):
        self.status = status
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        self.sock.settimeout(0.2)
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = snmp._read_tlv(data, 0)
                off = msg.value_start
                off = snmp._skip_tlv(data, off)  # version
                comm = snmp._read_tlv(data, off)
                community = data[comm.value_start:comm.value_end].decode()
                off = comm.value_end
                pdu = snmp._read_tlv(data, off)
                off = pdu.value_start
                req_id_tlv = snmp._read_tlv(data, off)
                req_id = int.from_bytes(data[req_id_tlv.value_start:req_id_tlv.value_end], "big")
                response = _build_error_response(req_id, community, self.status)
                self.sock.sendto(response, addr)
            except (ValueError, OSError):
                continue

    def close(self):
        self.running = False
        self.sock.close()


def _build_error_response(request_id: int, community: str, status: int = 2) -> bytes:
    """SNMPv2c GetResponse with the given error-status and NULL varbinds."""
    varbinds = b""
    for oid in snmp.OIDS.values():
        body = _encode_oid(oid) + b"\x05\x00"  # NULL value
        varbinds += b"\x30" + _encode_len(len(body)) + body
    vb_seq = b"\x30" + _encode_len(len(varbinds)) + varbinds
    body = (snmp._encode_integer(request_id) + snmp._encode_integer(status)
            + snmp._encode_integer(0) + vb_seq)
    pdu = b"\xa2" + _encode_len(len(body)) + body  # GetResponse-PDU
    msg = snmp._encode_integer(1) + _encode_str(community) + pdu
    return b"\x30" + _encode_len(len(msg)) + msg


@pytest.fixture
def error_agent():
    mock = ErrorAgent()
    yield mock
    mock.close()


@pytest.fixture
def empty_agent():
    mock = ErrorAgent(status=0)  # noError, but NULL varbinds (noSuchObject style)
    yield mock
    mock.close()


# ── Error-status handling (Sprint 5 regression) ──────────────────────────────

def test_parse_response_checked_reports_error_status():
    packet = _build_error_response(1, "bad", status=2)
    result, status = snmp.parse_response_checked(packet)
    assert status == 2
    assert set(result) == set(snmp.OIDS.values())
    assert all(v is None for v in result.values())


def test_parse_response_compat_ignores_error_status():
    packet = _build_error_response(1, "bad", status=2)
    result = snmp.parse_response(packet)
    assert set(result) == set(snmp.OIDS.values())


def test_snmp_poll_rejects_error_response(error_agent):
    result = snmp.snmp_poll("127.0.0.1", ["wrong"], timeout=0.4, port=error_agent.port)
    assert result is None  # an error PDU must not count as identified


def test_snmp_poll_rejects_valueless_response(empty_agent):
    result = snmp.snmp_poll("127.0.0.1", ["bad"], timeout=0.4, port=empty_agent.port)
    assert result is None  # no sysDescr/sysName/sysObjectID means not identified


# ── Request building ─────────────────────────────────────────────────────────

def test_build_get_request_encodes_v2c_header():
    pkt = snmp.build_get_request([snmp.OIDS["sysDescr"]], "public", 42)
    assert pkt[0] == 0x30                      # SEQUENCE
    assert pkt[2:5] == b"\x02\x01\x01"          # INTEGER version = 1 (v2c)
    assert pkt[5] == 0x04                       # OCTET STRING community
    assert b"public" in pkt


def test_build_get_request_multiple_oids():
    pkt = snmp.build_get_request(list(snmp.OIDS.values()), "public", 7)
    assert pkt.count(b"\x06\x08") == 3  # three 8-subid OIDs (one per varbind)


# ── Polling end-to-end ───────────────────────────────────────────────────────

def test_snmp_poll_returns_data(agent):
    result = snmp.snmp_poll("127.0.0.1", ["public"], timeout=1.0, port=agent.port)
    assert result is not None
    assert result["community"] == "public"
    assert result["sysName"] == "core-sw1"
    assert result["sysObjectID"] == ".1.3.6.1.4.1.9.1.2345"
    assert "C9300L" in result["sysDescr"]


def test_snmp_poll_tries_next_community(agent):
    result = snmp.snmp_poll("127.0.0.1", ["nope", "public"], timeout=0.4, port=agent.port)
    assert result is not None and result["community"] == "public"


def test_snmp_poll_returns_none_on_no_match(agent):
    result = snmp.snmp_poll("127.0.0.1", ["wrong"], timeout=0.4, port=agent.port)
    assert result is None


def test_snmp_poll_timeout_no_crash():
    result = snmp.snmp_poll("127.0.0.1", ["public"], timeout=0.3, port=1)
    assert result is None
