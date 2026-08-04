"""Start a mock SNMP agent on a fixed port with LLDP + CDP topology data.

Usage:
    cd backend && .venv/bin/python demo_mock.py [port]

This lets the frontend discover 127.0.0.1 and show topology links instantly.
"""

import sys
import time

sys.path.insert(0, ".")

from tests.test_topology import TopologyMockAgent

port = int(sys.argv[1]) if len(sys.argv) > 1 else 11161

agent = TopologyMockAgent()

# Rebind to the requested port.
# TopologyMockAgent already bound to an ephemeral port. We need a fresh agent.
# Workaround: create it with a custom socket.
import socket
import threading
from snmp import _read_tlv, _skip_tlv, _parse_oid, _encode_integer

def _enc_l(l):
    if l < 0x80: return bytes([l])
    b = bytearray()
    while l > 0:
        b.insert(0, l & 0xFF)
        l >>= 8
    return bytes([0x80 | len(b)]) + bytes(b)

def _seq(b): return b"\x30" + _enc_l(len(b)) + b
def _enc_oid(oid):
    parts = [int(p) for p in oid.lstrip(".").split(".")]
    p = bytearray([parts[0]*40+parts[1]])
    for part in parts[2:]:
        s = []
        while part >= 128:
            s.insert(0, part%128)
            part >>= 7
        s.insert(0, part)
        for i, b in enumerate(s):
            p.append(b | 0x80 if i < len(s) - 1 else b)
    return b"\x06" + _enc_l(len(p)) + bytes(p)

def _enc_val(v):
    if isinstance(v, bytes):
        return b"\x04" + _enc_l(len(v)) + v
    p = v.encode("latin-1")
    return b"\x04" + _enc_l(len(p)) + p

def _vb(o, v): return _seq(o + v)

def _oid_key(oid): return [int(p) for p in oid.split(".")]


class DemoMockAgent:
    MIB = {
        "1.3.6.1.2.1.1.1.0": b"sw1",
        "1.3.6.1.2.1.1.5.0": b"sw1",
        "1.0.8802.1.1.2.1.4.1.1.5.0.1.1": b"\x00\x11\x22\x33\x44\x55",
        "1.0.8802.1.1.2.1.4.1.1.7.0.1.1": b"Eth1/0/1",
        "1.0.8802.1.1.2.1.4.1.1.8.0.1.1": b"uplink to sw2",
        "1.0.8802.1.1.2.1.4.1.1.9.0.1.1": b"sw2",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.3.1.1": b"\x0a\x00\x00\x02",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.6.1.1": b"sw2",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.7.1.1": b"Eth1/0/1",
        "1.3.6.1.4.1.9.9.23.1.2.1.1.8.1.1": b"Cisco C9300",
    }
    _SORTED = sorted(MIB.keys(), key=_oid_key)

    def __init__(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", port))
        self.port = port
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
                resp = self._handle(data)
                if resp:
                    self.sock.sendto(resp, addr)
            except (ValueError, OSError):
                continue

    def _handle(self, data):
        msg = _read_tlv(data, 0)
        off = msg.value_start
        off = _skip_tlv(data, off)
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

        if pdu_tag == 0xA0:
            off = _skip_tlv(data, off)
            off = _skip_tlv(data, off)
            vb_seq = _read_tlv(data, off)
            oids = []
            inner = vb_seq.value_start
            while inner < vb_seq.value_end:
                bind = _read_tlv(data, inner)
                oid_tlv = _read_tlv(data, bind.value_start)
                oids.append(_parse_oid(data, oid_tlv.value_start, oid_tlv.value_end))
                inner = bind.value_end
            vbs = b"".join(_vb(_enc_oid(o), _enc_val(self.MIB.get(o, b""))) for o in oids)
        elif pdu_tag == 0xA5:
            off = _skip_tlv(data, off)
            maxrep_tlv = _read_tlv(data, off)
            max_rep = int.from_bytes(data[maxrep_tlv.value_start:maxrep_tlv.value_end], "big")
            off = maxrep_tlv.value_end
            vb_seq = _read_tlv(data, off)
            bind = _read_tlv(data, vb_seq.value_start)
            oid_tlv = _read_tlv(data, bind.value_start)
            start_oid = _parse_oid(data, oid_tlv.value_start, oid_tlv.value_end)
            entries = [o for o in self._SORTED if _oid_key(o) > _oid_key(start_oid)][:max(1, max_rep)]
            vbs = b"".join(_vb(_enc_oid(o), _enc_val(self.MIB[o])) for o in entries)
        else:
            return None

        vb_seq = _seq(vbs)
        body = _encode_integer(req_id) + _encode_integer(0) + _encode_integer(0) + vb_seq
        pdu = b"\xa2" + _enc_l(len(body)) + body
        msg = _encode_integer(1) + _enc_val(b"public") + pdu
        return _seq(msg)

    def close(self):
        self.running = False
        self.sock.close()


if __name__ == "__main__":
    demo = DemoMockAgent(port)
    print(f"Mock agent running on 127.0.0.1:{port}")
    print("Discover with: subnet=127.0.0.1/32, community=public, snmp_port={}".format(port))
    print("Press Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        demo.close()
        print("\nStopped")
