"""Sprint 3: pure-Python SNMPv3/USM client (RFC 3412/3414/3826)."""

import socket
import threading

import pytest

import snmpv3

ENGINE_ID = bytes.fromhex("000000000000000000000002")
AUTH_PW = "authpass123"
PRIV_PW = "privpass123"


# ── RFC 3414 key localization test vectors ───────────────────────────────────

def test_rfc3414_md5_localized_key():
    ku = snmpv3.password_to_key("md5", "maplesyrup")
    kul = snmpv3.localize_key("md5", ku, ENGINE_ID)
    assert kul.hex() == "526f5eed9fcce26f8964c2930787d82b"


def test_rfc3414_sha_localized_key():
    ku = snmpv3.password_to_key("sha", "maplesyrup")
    kul = snmpv3.localize_key("sha", ku, ENGINE_ID)
    assert kul.hex() == "6695febc9288e36282235fc7151f128497b38f3f"


def test_password_to_key_short_password_extended():
    ku = snmpv3.password_to_key("md5", "short")
    assert len(ku) == 16


# ── Crypto primitives ─────────────────────────────────────────────────────────

def test_des_privacy_round_trip():
    key = snmpv3.localize_key("md5", snmpv3.password_to_key("md5", PRIV_PW), ENGINE_ID)
    salt = bytes.fromhex("0000000054a52e65")
    plain = b"\x30\x00" * 4  # 8-byte plaintext
    ct = snmpv3._des_privacy_encrypt(key, salt, plain)
    assert len(ct) == 8
    assert snmpv3._des_privacy_decrypt(key, salt, ct) == plain


def test_aes_privacy_round_trip():
    key = snmpv3.localize_key("sha", snmpv3.password_to_key("sha", PRIV_PW), ENGINE_ID)
    salt = b"\x00" * 8
    plain = b"\x30\x00" * 16  # 32-byte plaintext
    ct = snmpv3._aes_privacy_encrypt(key, 1, 100, salt, plain)
    assert len(ct) == 32
    assert snmpv3._aes_privacy_decrypt(key, 1, 100, salt, ct) == plain


def test_auth_hmac_truncated_to_12():
    key = snmpv3.localize_key("sha", snmpv3.password_to_key("sha", AUTH_PW), ENGINE_ID)
    digest = snmpv3._auth_hmac("sha", key, b"message")
    assert len(digest) == 12


# ── Message structure ─────────────────────────────────────────────────────────

def test_build_message_v3_header():
    pkt = snmpv3.build_message(10, snmpv3.FLAG_REPORTABLE, b"", 0, 0,
                               b"testuser", b"", b"", b"\x30\x00")
    assert pkt[0] == 0x30
    # version INTEGER 3
    assert pkt[2:5] == b"\x02\x01\x03"
    # msgSecurityModel INTEGER 3
    assert b"\x02\x01\x03" in pkt


# ── End-to-end against a mock USM agent ──────────────────────────────────────

def _seq(body):
    return b"\x30" + snmpv3._encode_length(len(body)) + body


def _octets(v):
    return b"\x04" + snmpv3._encode_length(len(v)) + v


def _pdu(tag, body):
    return bytes([tag]) + snmpv3._encode_length(len(body)) + body


class MockV3Agent:
    """UDP SNMPv3 USM agent: discovery report + SHA/AES authed responses."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.engine_id = ENGINE_ID
        self.engine_boots = 1
        self.engine_time = 100
        self.auth_key = snmpv3.localize_key("sha", snmpv3.password_to_key("sha", AUTH_PW), self.engine_id)
        self.priv_key = snmpv3.localize_key("sha", snmpv3.password_to_key("sha", PRIV_PW), self.engine_id)
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
                self._handle(data, addr)
            except (ValueError, OSError, KeyError):
                continue

    def _handle(self, data, addr):
        resp = snmpv3.parse_v3_message(data)  # not authed yet at parse time
        if resp.engine_id == b"":
            # Discovery: answer with a usmStatsUnknownEngineIDs report.
            varbind = _seq(snmpv3._encode_oid(snmpv3.USM_STATS_UNKNOWN_ENGINE_IDS) + b"\x05\x00")
            pdu = _pdu(snmpv3.PDU_REPORT, snmpv3._int(resp.request_id) + snmpv3._int(0) + snmpv3._int(0) + _seq(varbind))
            scoped = _seq(_octets(self.engine_id) + _octets(b"") + pdu)
            msg = snmpv3.build_message(resp.msg_id, snmpv3.FLAG_REPORTABLE,
                                       self.engine_id, self.engine_boots, self.engine_time,
                                       resp.varbinds and b"testuser" or b"", b"", b"", scoped)
            self.sock.sendto(msg, addr)
            return

        # Authenticated request: verify + decrypt.
        snmpv3.parse_v3_message(data, "sha", self.auth_key)
        parsed = snmpv3.parse_v3_message(data)
        if parsed.flags & snmpv3.FLAG_PRIV:
            plain = snmpv3._decrypt_scoped_pdu(
                "aes", self.priv_key, parsed.engine_boots, parsed.engine_time,
                parsed.varbinds["_priv_salt"], parsed.varbinds["_priv_ciphertext"])
        else:
            plain = data[-len(snmpv3._seq(snmpv3._encode_oid(snmpv3.OIDS["sysDescr"]) + b"\x05\x00")):]
        req_id, _err, _vbs = snmpv3._parse_pdu(snmpv3._parse_scoped_pdu(plain))

        # Build the response.
        value = _octets(b"SNMPv3-Test-Agent")
        varbind = _seq(snmpv3._encode_oid(snmpv3.OIDS["sysDescr"]) + value)
        pdu = _pdu(snmpv3.PDU_RESPONSE, snmpv3._int(req_id) + snmpv3._int(0) + snmpv3._int(0) + _seq(varbind))
        scoped = _seq(_octets(self.engine_id) + _octets(b"") + pdu)
        flags = snmpv3.FLAG_REPORTABLE | snmpv3.FLAG_AUTH
        priv_params = b""
        if parsed.flags & snmpv3.FLAG_PRIV:
            flags |= snmpv3.FLAG_PRIV
            scoped, priv_params = snmpv3._encrypt_scoped_pdu(
                "aes", self.priv_key, self.engine_boots, self.engine_time,
                snmpv3._SaltGenerator().next(), scoped)
            scoped = _octets(scoped)
        msg = snmpv3.build_message(resp.msg_id, flags, self.engine_id, self.engine_boots,
                                   self.engine_time, b"testuser", b"\x00" * 12, priv_params, scoped)
        auth = snmpv3._auth_hmac("sha", self.auth_key, msg)
        msg = snmpv3.build_message(resp.msg_id, flags, self.engine_id, self.engine_boots,
                                   self.engine_time, b"testuser", auth, priv_params, scoped)
        self.sock.sendto(msg, addr)

    def close(self):
        self.running = False
        self.sock.close()


@pytest.fixture
def v3agent():
    agent = MockV3Agent()
    yield agent
    agent.close()


def test_snmpv3_get_sha_aes(v3agent):
    result = snmpv3.snmpv3_get(
        "127.0.0.1", username="testuser", auth_protocol="sha", auth_password=AUTH_PW,
        privacy_protocol="aes", privacy_password=PRIV_PW, timeout=1.0, port=v3agent.port)
    assert result is not None
    assert result["sysDescr"] == "SNMPv3-Test-Agent"
    assert result["community"] == ""


def test_snmpv3_get_wrong_password_returns_none(v3agent):
    result = snmpv3.snmpv3_get(
        "127.0.0.1", username="testuser", auth_protocol="sha", auth_password="wrongpass",
        privacy_protocol="aes", privacy_password=PRIV_PW, timeout=1.0, port=v3agent.port)
    assert result is None


def test_snmpv3_get_timeout_no_crash():
    result = snmpv3.snmpv3_get(
        "127.0.0.1", username="x", auth_protocol="sha", auth_password=AUTH_PW,
        privacy_protocol="none", timeout=0.3, port=1)
    assert result is None
