"""Pure-Python SNMPv3 client with USM security (RFC 3412/3414/3826).

Implements the full v3 message flow over UDP:
    - Engine discovery (report-driven, learns authoritative engineID/boots/time)
    - Key localization (RFC 3414) for MD5/SHA-1 auth and DES/AES-128 privacy
    - HMAC authentication (12-byte truncation)
    - DES-CBC (RFC 3414) and AES-128-CBC (RFC 3826) privacy
    - Timeliness resynchronization on usmStatsNotInTimeWindows reports

No SNMP library is used; crypto comes from the `cryptography` package
(which is already a dependency for at-rest credential encryption).
"""

from __future__ import annotations

import hashlib
import hmac
import random
import socket

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

try:
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    from cryptography.hazmat.decrepit.ciphers.modes import CFB
except ImportError:  # pragma: no cover - older cryptography versions
    TripleDES = algorithms.TripleDES
    CFB = modes.CFB

from snmp import _encode_integer, _read_tlv, _skip_tlv, _parse_oid, _parse_value, OIDS

AUTH_NONE = "none"
AUTH_MD5 = "md5"
AUTH_SHA = "sha"

PRIV_NONE = "none"
PRIV_DES = "des"
PRIV_AES = "aes"

USM_STATS_NOT_IN_TIME_WINDOWS = "1.3.6.1.6.3.15.1.1.1.0"
USM_STATS_UNKNOWN_ENGINE_IDS = "1.3.6.1.6.3.15.1.1.4.0"

DEFAULT_TIMEOUT = 2.0
DEFAULT_PORT = 161

FLAG_AUTH = 0x01
FLAG_PRIV = 0x02
FLAG_REPORTABLE = 0x04

PDU_GET = 0xA0
PDU_RESPONSE = 0xA2
PDU_REPORT = 0xA8


def _encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    body = bytearray()
    while length > 0:
        body.insert(0, length & 0xFF)
        length >>= 8
    return bytes([0x80 | len(body)]) + bytes(body)


def _seq(body: bytes) -> bytes:
    return b"\x30" + _encode_length(len(body)) + body


def _octets(value: bytes) -> bytes:
    return b"\x04" + _encode_length(len(value)) + value


def _int(value: int) -> bytes:
    return _encode_integer(value)


def _encode_oid(oid: str) -> bytes:
    from snmp import _encode_oid as _snmp_encode_oid

    return _snmp_encode_oid(oid)


# ── Key localization (RFC 3414) ──────────────────────────────────────────────

def _hash_for(proto: str):
    if proto == AUTH_MD5:
        return hashlib.md5
    if proto == AUTH_SHA:
        return hashlib.sha1
    raise ValueError(f"unsupported auth protocol: {proto}")


def password_to_key(auth_protocol: str, password: str) -> bytes:
    """RFC 3414 password-to-key (Ku): hash of the password padded to 1 MiB."""
    digest = _hash_for(auth_protocol)
    if len(password) < 8:
        password = (password * (8 // len(password) + 1))[:8]
    buf = (password * (1048576 // len(password) + 1))[:1048576]
    return digest(buf.encode("utf-8")).digest()


def localize_key(auth_protocol: str, key: bytes, engine_id: bytes) -> bytes:
    """RFC 3414 localized key: Kul = H(Ku || engineID || Ku)."""
    digest = _hash_for(auth_protocol)
    return digest(key + engine_id + key).digest()


# ── Message encoding ─────────────────────────────────────────────────────────

def _encode_varbind(oid: str) -> bytes:
    return _seq(_encode_oid(oid) + b"\x05\x00")  # NULL value for GET


def _encode_get_pdu(request_id: int, oid_list) -> bytes:
    varbinds = b"".join(_encode_varbind(oid) for oid in oid_list)
    body = _int(request_id) + _int(0) + _int(0) + _seq(varbinds)
    return bytes([PDU_GET]) + _encode_length(len(body)) + body


def _encode_scoped_pdu(engine_id: bytes, context_name: bytes, pdu: bytes) -> bytes:
    return _seq(_octets(engine_id) + _octets(context_name) + pdu)


def build_message(msg_id: int, flags: int, engine_id: bytes, engine_boots: int,
                  engine_time: int, username: bytes, auth_params: bytes,
                  priv_params: bytes, scoped_pdu: bytes) -> bytes:
    global_data = _seq(
        _int(msg_id) + _int(65507) + _octets(bytes([flags])) + _int(3)
    )
    usm = _seq(
        _octets(engine_id)
        + _int(engine_boots)
        + _int(engine_time)
        + _octets(username)
        + _octets(auth_params)
        + _octets(priv_params)
    )
    return _seq(_int(3) + global_data + _octets(usm) + scoped_pdu)


# ── Authentication / privacy ─────────────────────────────────────────────────

def _auth_hmac(auth_protocol: str, localized_key: bytes, message: bytes) -> bytes:
    digest = _hash_for(auth_protocol)
    return hmac.new(localized_key, message, digest).digest()[:12]


def _des_transform(key8: bytes, iv8: bytes, data: bytes, encrypt: bool) -> bytes:
    """Single DES via TripleDES with the key repeated three times."""
    cipher = Cipher(TripleDES(key8 * 3), modes.CBC(iv8))
    trans = cipher.encryptor() if encrypt else cipher.decryptor()
    return trans.update(data) + trans.finalize()


def _des_privacy_encrypt(localized_priv_key: bytes, salt: bytes, plaintext: bytes) -> bytes:
    key8 = localized_priv_key[:8]
    pre_iv = localized_priv_key[8:16]
    iv = bytes(a ^ b for a, b in zip(pre_iv, salt))
    padded = plaintext + b"\x00" * (-len(plaintext) % 8)
    return _des_transform(key8, iv, padded, True)


def _des_privacy_decrypt(localized_priv_key: bytes, salt: bytes, ciphertext: bytes) -> bytes:
    key8 = localized_priv_key[:8]
    pre_iv = localized_priv_key[8:16]
    iv = bytes(a ^ b for a, b in zip(pre_iv, salt))
    return _des_transform(key8, iv, ciphertext, False)


def _aes_privacy_encrypt(localized_priv_key: bytes, engine_boots: int, engine_time: int,
                         salt: bytes, plaintext: bytes) -> bytes:
    # RFC 3826: AES-CFB128, no padding; IV = boots(4) + time(4) + salt(8).
    key = localized_priv_key[:16]
    iv = engine_boots.to_bytes(4, "big") + engine_time.to_bytes(4, "big") + salt
    cipher = Cipher(algorithms.AES(key), CFB(iv))
    return cipher.encryptor().update(plaintext) + cipher.encryptor().finalize()


def _aes_privacy_decrypt(localized_priv_key: bytes, engine_boots: int, engine_time: int,
                         salt: bytes, ciphertext: bytes) -> bytes:
    key = localized_priv_key[:16]
    iv = engine_boots.to_bytes(4, "big") + engine_time.to_bytes(4, "big") + salt
    cipher = Cipher(algorithms.AES(key), CFB(iv))
    return cipher.decryptor().update(ciphertext) + cipher.decryptor().finalize()


def _encrypt_scoped_pdu(privacy_protocol: str, localized_priv_key: bytes,
                        engine_boots: int, engine_time: int, salt: bytes,
                        scoped_pdu: bytes) -> tuple[bytes, bytes]:
    if privacy_protocol == PRIV_DES:
        return _des_privacy_encrypt(localized_priv_key, salt, scoped_pdu), salt
    if privacy_protocol == PRIV_AES:
        return _aes_privacy_encrypt(localized_priv_key, engine_boots, engine_time, salt, scoped_pdu), salt
    raise ValueError(f"unsupported privacy protocol: {privacy_protocol}")


def _decrypt_scoped_pdu(privacy_protocol: str, localized_priv_key: bytes,
                        engine_boots: int, engine_time: int, salt: bytes,
                        ciphertext: bytes) -> bytes:
    if privacy_protocol == PRIV_DES:
        return _des_privacy_decrypt(localized_priv_key, salt, ciphertext)
    if privacy_protocol == PRIV_AES:
        return _aes_privacy_decrypt(localized_priv_key, engine_boots, engine_time, salt, ciphertext)
    raise ValueError(f"unsupported privacy protocol: {privacy_protocol}")


# ── Message parsing ──────────────────────────────────────────────────────────

class SnmpV3Response:
    def __init__(self, msg_id, flags, engine_id, engine_boots, engine_time,
                 pdu_tag, request_id, error_status, varbinds: dict):
        self.msg_id = msg_id
        self.flags = flags
        self.engine_id = engine_id
        self.engine_boots = engine_boots
        self.engine_time = engine_time
        self.pdu_tag = pdu_tag
        self.request_id = request_id
        self.error_status = error_status
        self.varbinds = varbinds

    @property
    def is_report(self) -> bool:
        return self.pdu_tag == PDU_REPORT

    @property
    def authed(self) -> bool:
        return bool(self.flags & FLAG_AUTH)


def _parse_varbinds(buf: bytes, vb_seq_start: int, vb_seq_end: int) -> dict:
    result: dict = {}
    offset = vb_seq_start
    while offset < vb_seq_end:
        bind = _read_tlv(buf, offset)
        inner = bind.value_start
        oid_tlv = _read_tlv(buf, inner)
        oid = _parse_oid(buf, oid_tlv.value_start, oid_tlv.value_end)
        inner = oid_tlv.value_end
        val_tlv = _read_tlv(buf, inner)
        result[oid] = _parse_value(val_tlv, buf)
        offset = bind.value_end
    return result


def _parse_pdu(buf: bytes):
    """Parse a PDU SEQUENCE into (request_id, error_status, varbinds)."""
    pdu = _read_tlv(buf, 0)
    offset = pdu.value_start
    req_id_tlv = _read_tlv(buf, offset)
    request_id = int.from_bytes(buf[req_id_tlv.value_start:req_id_tlv.value_end], "big")
    offset = req_id_tlv.value_end
    err_tlv = _read_tlv(buf, offset)
    error_status = int.from_bytes(buf[err_tlv.value_start:err_tlv.value_end], "big")
    offset = err_tlv.value_end
    err_idx = _read_tlv(buf, offset)
    offset = err_idx.value_end
    vb_seq = _read_tlv(buf, offset)
    varbinds = _parse_varbinds(buf, vb_seq.value_start, vb_seq.value_end)
    return request_id, error_status, varbinds


def _parse_scoped_pdu(buf: bytes) -> bytes:
    """Strip the contextEngineID/contextName prefix and return the PDU bytes."""
    scoped = _read_tlv(buf, 0)
    offset = scoped.value_start
    offset = _skip_tlv(buf, offset)  # contextEngineID
    offset = _skip_tlv(buf, offset)  # contextName
    return buf[offset:scoped.value_end]


def parse_v3_message(buf: bytes, auth_protocol: str = AUTH_NONE,
                     localized_auth_key: bytes | None = None) -> SnmpV3Response:
    """Decode and (optionally) verify an SNMPv3 message."""
    msg = _read_tlv(buf, 0)
    offset = msg.value_start
    offset = _skip_tlv(buf, offset)  # version
    global_abs_start = offset
    global_tlv = _read_tlv(buf, offset)
    goff = global_tlv.value_start
    msg_id_tlv = _read_tlv(buf, goff)
    msg_id = int.from_bytes(buf[msg_id_tlv.value_start:msg_id_tlv.value_end], "big")
    goff = msg_id_tlv.value_end
    goff = _skip_tlv(buf, goff)  # msgMaxSize
    flags_tlv = _read_tlv(buf, goff)
    flags = buf[flags_tlv.value_start]
    goff = flags_tlv.value_end
    goff = _skip_tlv(buf, goff)  # msgSecurityModel
    global_raw = buf[global_abs_start:global_tlv.value_end]
    offset = global_tlv.value_end

    sec_params_tlv = _read_tlv(buf, offset)
    sp = _read_tlv(buf, sec_params_tlv.value_start)
    soff = sp.value_start
    engine_id_tlv = _read_tlv(buf, soff)
    engine_id = buf[engine_id_tlv.value_start:engine_id_tlv.value_end]
    soff = engine_id_tlv.value_end
    boots_tlv = _read_tlv(buf, soff)
    engine_boots = int.from_bytes(buf[boots_tlv.value_start:boots_tlv.value_end], "big")
    soff = boots_tlv.value_end
    time_tlv = _read_tlv(buf, soff)
    engine_time = int.from_bytes(buf[time_tlv.value_start:time_tlv.value_end], "big")
    soff = time_tlv.value_end
    user_tlv = _read_tlv(buf, soff)
    username = buf[user_tlv.value_start:user_tlv.value_end]
    soff = user_tlv.value_end
    auth_tlv = _read_tlv(buf, soff)
    auth_params = buf[auth_tlv.value_start:auth_tlv.value_end]
    soff = auth_tlv.value_end
    priv_tlv = _read_tlv(buf, soff)
    priv_params = buf[priv_tlv.value_start:priv_tlv.value_end]
    msg_data_raw = buf[sec_params_tlv.value_end:msg.value_end]

    if flags & FLAG_AUTH and localized_auth_key is not None:
        # net-snmp (and the RFC 3414 reference code) computes the HMAC over
        # the message with a 12-byte zero-filled msgAuthenticationParameters.
        expected = _auth_hmac(
            auth_protocol, localized_auth_key,
            _seq(_int(3) + global_raw + _octets(_seq(_octets(engine_id) + _int(engine_boots)
                + _int(engine_time) + _octets(username) + _octets(b"\x00" * 12) + _octets(priv_params)))
                 + msg_data_raw),
        )
        if not hmac.compare_digest(expected, auth_params):
            raise ValueError("SNMPv3 message authentication failed")

    if flags & FLAG_PRIV:
        # msgData is an encrypted OCTET STRING wrapping the scoped PDU.
        msg_data_tlv = _read_tlv(buf, sec_params_tlv.value_end)
        ciphertext = buf[msg_data_tlv.value_start:msg_data_tlv.value_end]
        return SnmpV3Response(msg_id, flags, engine_id, engine_boots, engine_time,
                              PDU_REPORT, 0, 0, {"_priv_ciphertext": ciphertext,
                                                  "_priv_salt": priv_params})

    pdu_bytes = _parse_scoped_pdu(msg_data_raw)
    pdu_tlv = _read_tlv(pdu_bytes, 0)
    request_id, error_status, varbinds = _parse_pdu(pdu_bytes)
    return SnmpV3Response(msg_id, flags, engine_id, engine_boots, engine_time,
                          pdu_tlv.type, request_id, error_status, varbinds)


def _decrypt_response(resp: SnmpV3Response, privacy_protocol: str,
                      localized_priv_key: bytes) -> SnmpV3Response:
    """Decrypt an encrypted response into a fully parsed SnmpV3Response."""
    ciphertext = resp.varbinds["_priv_ciphertext"]
    salt = resp.varbinds["_priv_salt"]
    plaintext = _decrypt_scoped_pdu(privacy_protocol, localized_priv_key,
                                    resp.engine_boots, resp.engine_time, salt, ciphertext)
    pdu_bytes = _parse_scoped_pdu(plaintext)
    pdu_tlv = _read_tlv(pdu_bytes, 0)
    request_id, error_status, varbinds = _parse_pdu(pdu_bytes)
    return SnmpV3Response(resp.msg_id, resp.flags, resp.engine_id, resp.engine_boots,
                          resp.engine_time, pdu_tlv.type, request_id, error_status, varbinds)


# ── Client ───────────────────────────────────────────────────────────────────

def _recv(sock: socket.socket) -> bytes:
    data, _ = sock.recvfrom(65535)
    return data


def _send_and_recv(sock: socket.socket, host: str, port: int, packet: bytes) -> bytes:
    sock.sendto(packet, (host, port))
    return _recv(sock)


def _build_authed_request(msg_id: int, request_id: int, oid_list, username: bytes,
                          engine_id: bytes, engine_boots: int, engine_time: int,
                          auth_protocol: str, localized_auth_key: bytes | None,
                          privacy_protocol: str, localized_priv_key: bytes | None,
                          salt: bytes) -> bytes:
    flags = FLAG_REPORTABLE
    if auth_protocol != AUTH_NONE:
        flags |= FLAG_AUTH
    if privacy_protocol != PRIV_NONE:
        flags |= FLAG_PRIV

    pdu = _encode_get_pdu(request_id, oid_list)
    scoped = _encode_scoped_pdu(engine_id, b"", pdu)
    priv_params = b""
    if flags & FLAG_PRIV:
        scoped, priv_params = _encrypt_scoped_pdu(
            privacy_protocol, localized_priv_key, engine_boots, engine_time, salt, scoped
        )
        scoped = _octets(scoped)

    auth_params = b"\x00" * 12
    msg = build_message(msg_id, flags, engine_id, engine_boots, engine_time,
                        username, auth_params, priv_params, scoped)
    if flags & FLAG_AUTH:
        auth_params = _auth_hmac(auth_protocol, localized_auth_key, msg)
        msg = build_message(msg_id, flags, engine_id, engine_boots, engine_time,
                            username, auth_params, priv_params, scoped)
    return msg


class _SaltGenerator:
    def __init__(self):
        self._value = random.getrandbits(56)

    def next(self) -> bytes:
        self._value = (self._value + 1) % (2 ** 56)
        return self._value.to_bytes(8, "big")


def snmpv3_get(host: str, username: str, auth_protocol: str = AUTH_SHA,
               auth_password: str = "", privacy_protocol: str = PRIV_AES,
               privacy_password: str | None = None, oid_list=None,
               timeout: float = DEFAULT_TIMEOUT, port: int = DEFAULT_PORT) -> dict | None:
    """Perform an SNMPv3 GET, including engine discovery, and return varbinds."""
    oid_list = oid_list or [OIDS["sysDescr"], OIDS["sysObjectID"], OIDS["sysName"]]
    privacy_password = privacy_password if privacy_password is not None else auth_password

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    salt_gen = _SaltGenerator()
    try:
        # ── Phase 1: engine discovery (unauthenticated report) ────────────────
        engine_id, engine_boots, engine_time = _discover(
            sock, host, port, username, oid_list, timeout, salt_gen
        )

        # ── Phase 2: localize keys ────────────────────────────────────────────
        localized_auth_key = None
        if auth_protocol != AUTH_NONE:
            localized_auth_key = localize_key(
                auth_protocol, password_to_key(auth_protocol, auth_password), engine_id
            )
        localized_priv_key = None
        if privacy_protocol != PRIV_NONE:
            # net-snmp localizes the privacy key with the AUTH protocol's hash
            # (it deviates from RFC 3414's "use MD5 for DES"), so use the auth
            # hash for both DES and AES localization to match live agents.
            priv_hash_proto = auth_protocol
            localized_priv_key = localize_key(
                priv_hash_proto,
                password_to_key(priv_hash_proto, privacy_password),
                engine_id,
            )

        # ── Phase 3: authenticated request, resync on notInTimeWindows ────────
        for _attempt in range(2):
            msg_id = random.getrandbits(31)
            request_id = random.getrandbits(31)
            packet = _build_authed_request(
                msg_id, request_id, oid_list, username.encode("utf-8"),
                engine_id, engine_boots, engine_time,
                auth_protocol, localized_auth_key,
                privacy_protocol, localized_priv_key, salt_gen.next(),
            )
            try:
                data = _send_and_recv(sock, host, port, packet)
            except socket.timeout:
                return None
            resp = parse_v3_message(data, auth_protocol, localized_auth_key)
            if resp.flags & FLAG_PRIV:
                resp = _decrypt_response(resp, privacy_protocol, localized_priv_key)

            if resp.is_report:
                oid = next(iter(resp.varbinds), "")
                if oid == USM_STATS_NOT_IN_TIME_WINDOWS or oid == USM_STATS_UNKNOWN_ENGINE_IDS:
                    engine_boots, engine_time = resp.engine_boots, resp.engine_time
                    if resp.engine_id:
                        engine_id = resp.engine_id
                    continue
                raise ValueError(f"SNMPv3 report for request: {resp.varbinds}")

            if resp.error_status == 0 and resp.request_id == request_id:
                return {
                    "sysName": resp.varbinds.get(OIDS["sysName"], ""),
                    "sysDescr": resp.varbinds.get(OIDS["sysDescr"], ""),
                    "sysObjectID": resp.varbinds.get(OIDS["sysObjectID"], ""),
                    "community": "",
                }
            return None
        return None
    except (socket.timeout, OSError, ValueError):
        return None
    finally:
        sock.close()


def _discover(sock: socket.socket, host: str, port: int, username: str, oid_list,
              timeout: float, salt_gen: _SaltGenerator) -> tuple[bytes, int, int]:
    """Exchange discovery report and return (engine_id, engine_boots, engine_time)."""
    msg_id = random.getrandbits(31)
    request_id = random.getrandbits(31)
    pdu = _encode_get_pdu(request_id, oid_list)
    scoped = _encode_scoped_pdu(b"", b"", pdu)
    packet = build_message(msg_id, FLAG_REPORTABLE, b"", 0, 0,
                           username.encode("utf-8"), b"", b"", scoped)
    data = _send_and_recv(sock, host, port, packet)
    resp = parse_v3_message(data)
    if not resp.is_report:
        # Some agents reply with a plain response if they already know us.
        return resp.engine_id, resp.engine_boots, resp.engine_time
    engine_id = resp.engine_id or b""
    if not engine_id:
        raise ValueError("SNMPv3 discovery returned no authoritative engine ID")
    return engine_id, resp.engine_boots, resp.engine_time
