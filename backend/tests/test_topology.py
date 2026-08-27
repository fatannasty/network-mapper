"""Sprint 5: LLDP/CDP neighbor parsing, collection, and link building."""

from __future__ import annotations

import socket
import threading

import pytest

import scanner
import topology
from snmp import _encode_integer, _read_tlv, _skip_tlv, _parse_oid
from tests.test_snmpv3 import MockV3Agent, AUTH_PW, PRIV_PW


# ── Mock v2c agent with GET + GETBULK over an in-memory MIB ─────────────────

def _enc_len(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    body = bytearray()
    while length > 0:
        body.insert(0, length & 0xFF)
        length >>= 8
    return bytes([0x80 | len(body)]) + bytes(body)


def _enc_oid(oid: str) -> bytes:
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
    return b"\x06" + _enc_len(len(payload)) + bytes(payload)


def _enc_val(value) -> bytes:
    if isinstance(value, bytes):
        return b"\x04" + _enc_len(len(value)) + value
    payload = value.encode("latin-1")
    return b"\x04" + _enc_len(len(payload)) + payload


def _oid_key(oid: str) -> list[int]:
    return [int(p) for p in oid.split(".")]


def _vb(oid_bytes: bytes, val_bytes: bytes) -> bytes:
    body = oid_bytes + val_bytes
    return b"\x30" + _enc_len(len(body)) + body


def _seq(body: bytes) -> bytes:
    return b"\x30" + _enc_len(len(body)) + body


class TopologyMockAgent:
    """UDP v2c agent answering GET and GETBULK from a small MIB."""

    MIB = {
        "1.3.6.1.2.1.1.1.0": b"sw1",
        "1.3.6.1.2.1.1.5.0": b"sw1",
        # LLDP remote table (localPort 1 -> sw2, localPort 2 -> core-r1)
        "1.0.8802.1.1.2.1.4.1.1.5.0.1.1": b"\x00\x11\x22\x33\x44\x55",
        "1.0.8802.1.1.2.1.4.1.1.7.0.1.1": b"Eth1/0/1",
        "1.0.8802.1.1.2.1.4.1.1.8.0.1.1": b"uplink to sw2",
        "1.0.8802.1.1.2.1.4.1.1.9.0.1.1": b"sw2",
        "1.0.8802.1.1.2.1.4.1.1.9.0.2.1": b"core-r1",
        # CDP cache (ifIndex 1 -> sw2@10.0.0.2)
        "1.3.6.1.4.1.9.9.23.1.2.1.1.3.1.1": b"\x0a\x00\x00\x02",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.6.1.1": b"sw2",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.7.1.1": b"Eth1/0/1",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.8.1.1": b"Cisco C9300",
    }
    _SORTED = sorted(MIB.keys(), key=lambda o: list(map(int, o.split("."))))

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
                response = self._handle(data)
                if response:
                    self.sock.sendto(response, addr)
            except (ValueError, OSError):
                continue

    def _handle(self, data: bytes) -> bytes | None:
        msg = _read_tlv(data, 0)
        off = msg.value_start
        off = _skip_tlv(data, off)  # version
        comm = _read_tlv(data, off)
        if data[comm.value_start:comm.value_end].decode() != "public":
            return None
        off = comm.value_end
        pdu = _read_tlv(data, off)
        pdu_tag = pdu.type
        off = pdu.value_start
        req_tlv = _read_tlv(data, off)
        req_id = int.from_bytes(data[req_tlv.value_start:req_tlv.value_end], "big")
        off = req_tlv.value_end

        if pdu_tag == 0xA0:  # GET
            off = _skip_tlv(data, off)  # error-status
            off = _skip_tlv(data, off)  # error-index
            vb_seq = _read_tlv(data, off)
            oids = []
            inner = vb_seq.value_start
            while inner < vb_seq.value_end:
                bind = _read_tlv(data, inner)
                oid_tlv = _read_tlv(data, bind.value_start)
                oids.append(_parse_oid(data, oid_tlv.value_start, oid_tlv.value_end))
                inner = bind.value_end
            vbs = b"".join(_vb(_enc_oid(oid), _enc_val(self.MIB.get(oid, b""))) for oid in oids)
        elif pdu_tag == 0xA5:  # GETBULK
            off = _skip_tlv(data, off)  # non-repeaters
            maxrep_tlv = _read_tlv(data, off)
            max_rep = int.from_bytes(data[maxrep_tlv.value_start:maxrep_tlv.value_end], "big")
            off = maxrep_tlv.value_end
            vb_seq = _read_tlv(data, off)
            bind = _read_tlv(data, vb_seq.value_start)
            oid_tlv = _read_tlv(data, bind.value_start)
            start_oid = _parse_oid(data, oid_tlv.value_start, oid_tlv.value_end)
            entries = [o for o in self._SORTED if _oid_key(o) > _oid_key(start_oid)][:max(1, max_rep)]
            vbs = b"".join(_vb(_enc_oid(oid), _enc_val(self.MIB[oid])) for oid in entries)
        else:
            return None

        vb_seq = _seq(vbs)
        body = _encode_integer(req_id) + _encode_integer(0) + _encode_integer(0) + vb_seq
        pdu = b"\xa2" + _enc_len(len(body)) + body
        msg = _encode_integer(1) + _enc_val(b"public") + pdu
        return _seq(msg)

    def close(self):
        self.running = False
        self.sock.close()


@pytest.fixture
def agent():
    mock = TopologyMockAgent()
    yield mock
    mock.close()


@pytest.fixture
def v3agent():
    mock = MockV3Agent()
    yield mock
    mock.close()


# ── Parsing (pure, no network) ───────────────────────────────────────────────

def test_parse_lldp_neighbors():
    raw = {
        "1.0.8802.1.1.2.1.4.1.1.5.0.1.1": b"\x00\x11\x22\x33\x44\x55",
        "1.0.8802.1.1.2.1.4.1.1.7.0.1.1": b"Eth1/0/1",
        "1.0.8802.1.1.2.1.4.1.1.8.0.1.1": b"uplink to sw2",
        "1.0.8802.1.1.2.1.4.1.1.9.0.1.1": b"sw2",
        "1.0.8802.1.1.2.1.4.1.1.9.0.2.1": b"core-r1",
    }
    neighbors = topology.parse_lldp_neighbors(raw)
    assert len(neighbors) == 2
    by_port = {n["local_port"]: n for n in neighbors}
    n = by_port["1"]
    assert n["protocol"] == "lldp"
    assert n["remote_sysname"] == "sw2"
    assert n["remote_chassis_id"] == "00:11:22:33:44:55"
    assert n["remote_port_id"] == "45:74:68:31:2f:30:2f:31"  # hex of b"Eth1/0/1"
    assert n["remote_port_desc"] == "uplink to sw2"
    assert by_port["2"]["remote_sysname"] == "core-r1"


def test_parse_cdp_neighbors():
    raw = {
        "1.3.6.1.4.1.9.9.23.1.2.1.1.3.1.1": b"\x0a\x00\x00\x02",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.6.1.1": b"sw2",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.7.1.1": b"Eth1/0/1",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.8.1.1": b"Cisco C9300",
    }
    neighbors = topology.parse_cdp_neighbors(raw)
    assert len(neighbors) == 1
    n = neighbors[0]
    assert n["protocol"] == "cdp"
    assert n["local_port"] == "1"
    assert n["remote_device_id"] == "sw2"
    assert n["remote_ip"] == "10.0.0.2"
    assert n["remote_port"] == "Eth1/0/1"
    assert n["remote_platform"] == "Cisco C9300"


# ── Link building ────────────────────────────────────────────────────────────

def test_build_links_lldp_bidirectional_dedup():
    devices = [
        {"ip": "10.0.0.1", "hostname": "sw1",
         "interfaces": [{"ifIndex": "1", "ifDescr": "Gi1/0/1"}],
         "neighbors": [{"protocol": "lldp", "local_port": "1", "remote_sysname": "sw2",
                        "remote_port_desc": "Gi1/0/1", "remote_port_id": "",
                        "remote_chassis_id": ""}]},
        {"ip": "10.0.0.2", "hostname": "sw2", "interfaces": [],
         "neighbors": [{"protocol": "lldp", "local_port": "1", "remote_sysname": "sw1",
                        "remote_port_desc": "Gi1/0/1", "remote_port_id": "",
                        "remote_chassis_id": ""}]},
    ]
    links = topology.build_links(devices)
    assert len(links) == 1
    link = links[0]
    assert link["source"] == "10.0.0.1"
    assert link["target"] == "10.0.0.2"
    assert link["source_interface"] == "Gi1/0/1"
    assert link["target_interface"] == "Gi1/0/1"
    assert link["protocol"] == "lldp"
    assert link["source_hostname"] == "sw1"
    assert link["target_hostname"] == "sw2"


def test_build_links_cdp_matches_by_ip():
    devices = [
        {"ip": "10.0.0.1", "hostname": "sw1", "interfaces": [],
         "neighbors": [{"protocol": "cdp", "local_port": "1", "remote_device_id": "sw2",
                        "remote_port": "Eth1/0/1", "remote_ip": "10.0.0.2"}]},
        {"ip": "10.0.0.2", "hostname": "sw2", "interfaces": [], "neighbors": []},
    ]
    links = topology.build_links(devices)
    assert len(links) == 1
    assert links[0]["source"] == "10.0.0.1"
    assert links[0]["target"] == "10.0.0.2"
    assert links[0]["protocol"] == "cdp"


def test_build_links_unmatched_target_uses_name():
    devices = [
        {"ip": "10.0.0.1", "hostname": "sw1", "interfaces": [],
         "neighbors": [{"protocol": "lldp", "local_port": "1", "remote_sysname": "unknown-sw",
                        "remote_port_desc": "Te0/1", "remote_port_id": "", "remote_chassis_id": ""}]},
    ]
    links = topology.build_links(devices)
    assert len(links) == 1
    assert links[0]["target"] == "unknown-sw"
    assert links[0]["target_hostname"] == "unknown-sw"


# ── v2c collection end-to-end ────────────────────────────────────────────────

def test_collect_lldp_v2c(agent):
    neighbors = topology.collect_lldp_v2c("127.0.0.1", "public", port=agent.port, timeout=1.0)
    assert len(neighbors) == 2
    n = next(x for x in neighbors if x["local_port"] == "1")
    assert n["remote_sysname"] == "sw2"
    assert n["remote_chassis_id"] == "00:11:22:33:44:55"
    assert n["remote_port_desc"] == "uplink to sw2"


def test_collect_cdp_v2c(agent):
    neighbors = topology.collect_cdp_v2c("127.0.0.1", "public", port=agent.port, timeout=1.0)
    assert len(neighbors) == 1
    assert neighbors[0]["remote_ip"] == "10.0.0.2"
    assert neighbors[0]["remote_platform"] == "Cisco C9300"


def test_collect_lldp_cdp_v3(v3agent):
    kwargs = dict(auth_protocol="sha", auth_password=AUTH_PW,
                  privacy_protocol="aes", privacy_password=PRIV_PW,
                  port=v3agent.port, timeout=1.0)
    lldp = topology.collect_lldp_v3("127.0.0.1", "testuser", **kwargs)
    cdp = topology.collect_cdp_v3("127.0.0.1", "testuser", **kwargs)
    assert any(n["remote_sysname"] == "sw2" for n in lldp)
    assert any(n["remote_ip"] == "10.0.0.2" for n in cdp)


# ── Scanner wiring ───────────────────────────────────────────────────────────

def test_scanner_collect_topology_v2c(agent):
    devices = [{
        "ip": "127.0.0.1", "hostname": "sw1", "snmp_identified": True,
        "snmp_community": "public", "interfaces": [{"ifIndex": "1", "ifDescr": "Gi1/0/1"}],
    }]
    neighbors = scanner.collect_topology(devices, communities=["public"],
                                         snmp_port=agent.port, timeout=1.0)
    assert "127.0.0.1" in neighbors
    protos = {n["protocol"] for n in neighbors["127.0.0.1"]}
    assert protos == {"lldp", "cdp"}


def test_scanner_collect_topology_v3(v3agent):
    params = {"username": "testuser", "auth_protocol": "sha", "auth_password": AUTH_PW,
              "privacy_protocol": "aes", "privacy_password": PRIV_PW}
    devices = [{"ip": "127.0.0.1", "hostname": "sw1", "snmp_identified": True,
                "snmp_community": "", "interfaces": []}]
    neighbors = scanner.collect_topology(devices, communities=["public"],
                                         snmpv3=params, snmp_port=v3agent.port, timeout=1.0)
    assert "127.0.0.1" in neighbors
    protos = {n["protocol"] for n in neighbors["127.0.0.1"]}
    assert protos == {"lldp", "cdp"}


def test_walk_report_returns_interfaces_and_links():
    from database import SessionLocal
    from models import Device, Interface, Link
    from conftest import make_client
    import main

    client = make_client("admin")

    with SessionLocal() as db:
        db.query(Device).filter(Device.site == "WalkTestSite").delete()
        d1 = Device(ip="10.20.0.1", hostname="SW-A", device_type="switch", site="WalkTestSite")
        d2 = Device(ip="10.20.0.2", hostname="SW-B", device_type="switch", site="WalkTestSite")
        d3 = Device(ip="10.20.0.3", hostname="SW-C", device_type="switch", site="Denver")
        db.add_all([d1, d2, d3])
        db.flush()
        db.add_all([
            Interface(device_id=d1.id, if_name="Gi1/0/1", if_oper_status="up", vlan_id=90, vlan_name="Voice"),
            Interface(device_id=d3.id, if_name="Gi1/0/1", if_oper_status="up"),
            Link(scan_id="scan-w", endpoint_a=d1.ip, endpoint_b=d2.ip, protocol="lldp", interface_a="Gi1/0/1", interface_b="Gi1/0/1"),
            Link(scan_id="scan-w", endpoint_a=d1.ip, endpoint_b=d3.ip, protocol="lldp", interface_a="Gi1/0/2", interface_b="Gi1/0/2"),
        ])
        db.commit()

    resp = client.get("/api/topology/walk-report", params={"site": "WalkTestSite"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["interface_count"] == 1
    assert data["link_count"] == 1
    assert data["interfaces"][0]["vlan_id"] == 90
    assert data["interfaces"][0]["vlan_name"] == "Voice"
    assert data["links"][0]["protocol"] == "lldp"

    resp_all = client.get("/api/topology/walk-report")
    assert resp_all.json()["interface_count"] >= 2
    assert resp_all.json()["link_count"] >= 2


def test_cdp_neighbor_report_filters_access_points(monkeypatch):
    from conftest import make_client
    from database import SessionLocal
    from models import Device
    import backfill

    with SessionLocal() as db:
        db.query(Device).filter(Device.site == "CdpSite").delete()
        db.add(Device(ip="10.40.0.1", hostname="SW1", device_type="core-switch", site="CdpSite"))
        db.add(Device(ip="10.40.0.2", hostname="SW2", device_type="switch", site="CdpSite"))
        db.add(Device(ip="10.40.0.9", hostname="AP1", device_type="access-point", site="CdpSite"))
        db.commit()

    def fake_cdp(host, community, port=161, timeout=2.0):
        if host == "10.40.0.1":
            return [
                {"remote_device_id": "SW2", "remote_ip": "10.40.0.2",
                 "remote_port": "Gi1/0/1", "local_port": "1",
                 "remote_platform": "C9300", "remote_capabilities": 8},   # switch
                {"remote_device_id": "AP1", "remote_ip": "10.40.0.9",
                 "remote_port": "Gi1/0/24", "local_port": "2",
                 "remote_platform": "AIR-AP", "remote_capabilities": 16}, # host/AP
            ]
        return []

    monkeypatch.setattr("topology.collect_cdp_v2c", fake_cdp)
    client = make_client("operator")
    resp = client.post("/api/cdp/report", json={"site": "CdpSite"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["switches_checked"] == 1
    assert data["neighbors_found"] == 2
    assert data["excluded"] == 1  # the AP
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["switch_hostname"] == "SW1"
    assert row["neighbor_hostname"] == "SW2"
    assert row["neighbor_ip"] == "10.40.0.2"


def test_cdp_cli_parser_and_ssh_report(monkeypatch):
    from conftest import make_client
    from database import SessionLocal
    from models import Device
    from cdp_cli import parse_cdp_neighbors_detail
    import backfill

    sample = """
-------------------------
Device ID: SW2.amtrak.ad.nrpc
Entry address(es):
  IP address: 10.40.1.2
Platform: cisco C9300-24P,  Capabilities: Switch IGMP
Interface: Gi1/0/1,  Port ID (outgoing port): Gi1/0/2
Holdtime : 122 sec
-------------------------
Device ID: AP1
Entry address(es):
  IP address: 10.40.1.9
Platform: Cisco AIR-AP1832I, Capabilities: Host
Interface: Gi1/0/24,  Port ID (outgoing port): Gi1/0/1
"""
    parsed = parse_cdp_neighbors_detail(sample)
    assert len(parsed) == 2
    sw = next(n for n in parsed if n["remote_device_id"].startswith("SW2"))
    assert sw["remote_ip"] == "10.40.1.2"
    assert sw["remote_platform"] == "cisco C9300-24P"
    assert sw["local_port"] == "Gi1/0/1"
    assert sw["remote_port"] == "Gi1/0/2"
    assert sw["remote_capabilities"] & 0x08  # switch bit

    with SessionLocal() as db:
        db.query(Device).filter(Device.site == "CdpCliSite").delete()
        db.add(Device(ip="10.40.1.1", hostname="SW1", device_type="core-switch", site="CdpCliSite"))
        db.add(Device(ip="10.40.1.2", hostname="SW2", device_type="switch", site="CdpCliSite"))
        db.commit()

    def _fake_ssh_cdp(ip, *a, **k):
        return parse_cdp_neighbors_detail(sample) if ip == "10.40.1.1" else []

    monkeypatch.setattr("cdp_cli.collect_cdp_neighbors_detail", _fake_ssh_cdp)
    client = make_client("operator")
    resp = client.post("/api/cdp/report", json={
        "method": "ssh", "site": "CdpCliSite",
        "ssh_username": "user", "ssh_password": "pass",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["switches_checked"] == 1
    assert data["excluded"] == 1          # AP excluded
    assert len(data["rows"]) == 1
    assert data["rows"][0]["neighbor_hostname"].startswith("SW2")
