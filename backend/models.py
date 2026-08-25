"""SQLAlchemy ORM models: Devices, ScanJobs, Credentials, Sites."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from database import Base
from security import decrypt_secret, encrypt_secret


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EncryptedString(TypeDecorator):
    """Text column whose contents are encrypted at rest (Fernet).

    Legacy plaintext values decrypt transparently (pass-through), so an
    existing database needs no migration.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_secret(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_secret(value)


class Device(Base):
    """Persisted device inventory entry, keyed on IP address."""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    ip = Column(String(45), nullable=False, unique=True, index=True)
    mac = Column(String(17), default="")
    hostname = Column(String(255), default="", index=True)
    vendor = Column(String(100), default="", index=True)
    model = Column(Text, default="")
    device_type = Column(String(50), default="", index=True)
    confidence = Column(Integer, default=0)
    open_ports = Column(JSON, default=list)
    snmp_community = Column(String(64), default="")
    site = Column(String(255), default="", index=True)
    catalyst_id = Column(String(64), default="", index=True)

    last_scan_id = Column(String(32), ForeignKey("scan_jobs.id"), nullable=True)
    first_seen = Column(DateTime, default=_utcnow)
    last_seen = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    latency_ms = Column(Float, default=0.0)
    latency_checked_at = Column(DateTime, nullable=True)
    vlan_90 = Column(Boolean, nullable=True)  # running-config references VLAN 90

    interfaces = relationship(
        "Interface",
        backref="device",
        cascade="all, delete-orphan",
        order_by="Interface.if_index",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ip": self.ip,
            "mac": self.mac,
            "hostname": self.hostname,
            "vendor": self.vendor,
            "model": self.model,
            "device_type": self.device_type,
            "confidence": self.confidence,
            "open_ports": self.open_ports or [],
            "snmp_community": self.snmp_community,
            "site": self.site,
            "catalyst_id": self.catalyst_id,
            "last_scan_id": self.last_scan_id,
            "interfaces": [i.to_dict() for i in self.interfaces],
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "latency_ms": self.latency_ms or 0.0,
            "latency_checked_at": self.latency_checked_at.isoformat() if self.latency_checked_at else None,
            "vlan_90": self.vlan_90,
        }


class Interface(Base):
    """A network interface discovered via the IF-MIB walk (Sprint 4)."""

    __tablename__ = "interfaces"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    if_index = Column(String(16), default="")
    if_descr = Column(String(128), default="")
    if_name = Column(String(128), default="")
    if_type = Column(String(32), default="")
    if_speed = Column(String(32), default="")
    if_phys_address = Column(String(64), default="")
    if_admin_status = Column(String(16), default="")
    if_oper_status = Column(String(16), default="")
    if_high_speed = Column(String(32), default="")
    if_alias = Column(String(255), default="")
    vlan_id = Column(Integer, nullable=True)
    vlan_name = Column(String(128), default="")

    def to_dict(self) -> dict:
        return {
            "ifIndex": self.if_index,
            "ifDescr": self.if_descr,
            "ifName": self.if_name,
            "ifType": self.if_type,
            "ifSpeed": self.if_speed,
            "ifPhysAddress": self.if_phys_address,
            "ifAdminStatus": self.if_admin_status,
            "ifOperStatus": self.if_oper_status,
            "ifHighSpeed": self.if_high_speed,
            "ifAlias": self.if_alias,
            "vlanId": self.vlan_id,
            "vlanName": self.vlan_name,
        }


class DeviceStatusHistory(Base):
    """Reachability status transitions, used to detect up/down flapping."""

    __tablename__ = "device_status_history"

    id = Column(Integer, primary_key=True)
    ip = Column(String(45), nullable=False, index=True)
    status = Column(String(16), nullable=False)  # up | down
    observed_at = Column(DateTime, default=_utcnow, index=True)


class ScanJob(Base):
    """A discovery run: status, targets, and result counts."""

    __tablename__ = "scan_jobs"

    id = Column(String(32), primary_key=True)
    subnet = Column(String(64), nullable=False)
    communities = Column(JSON, default=list)
    exclude_pcs = Column(Boolean, default=True)
    status = Column(String(16), default="running", index=True)
    local_ip = Column(String(45), default="")
    snmpv3_username = Column(String(64), default="", index=True)
    scan_kind = Column(String(64), default="subnet", index=True)  # full_env | site:<name> | subnet
    scanned_hosts = Column(Integer, default=0)
    alive_hosts = Column(Integer, default=0)
    device_count = Column(Integer, default=0)
    snmp_identified = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=_utcnow)
    finished_at = Column(DateTime, nullable=True)
    diagram_topology = Column(String(16), default="auto")
    diagram_link_detail = Column(String(16), default="full")

    devices = relationship("Device", backref="scan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subnet": self.subnet,
            "communities": self.communities or [],
            "exclude_pcs": self.exclude_pcs,
            "status": self.status,
            "local_ip": self.local_ip,
            "snmpv3_username": self.snmpv3_username,
            "scan_kind": self.scan_kind,
            "scanned_hosts": self.scanned_hosts,
            "alive_hosts": self.alive_hosts,
            "device_count": self.device_count,
            "snmp_identified": self.snmp_identified,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class Credential(Base):
    """Stored device credentials, encrypted at rest (Sprint 3).

    Secrets never leave the API: password and snmp_community are only ever
    returned in encrypted form (and the default to_dict omits them entirely).
    """

    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    credential_type = Column(String(32), default="snmp")  # snmp | ssh | api
    username = Column(String(128), default="")
    password = Column(EncryptedString(), default="")
    snmp_community = Column(EncryptedString(), default="")
    site = Column(String(255), default="", index=True)
    created_at = Column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "credential_type": self.credential_type,
            "username": self.username,
            "site": self.site,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Site(Base):
    """Named locations (e.g. an Amtrak station) that devices belong to."""

    __tablename__ = "sites"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    location = Column(String(255), default="")
    created_at = Column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Link(Base):
    """A topology link between two devices, discovered via LLDP/CDP (Sprint 5)."""

    __tablename__ = "links"

    id = Column(Integer, primary_key=True)
    scan_id = Column(String(32), ForeignKey("scan_jobs.id"), nullable=False, index=True)
    endpoint_a = Column(String(128), nullable=False, index=True)
    endpoint_b = Column(String(128), nullable=False, index=True)
    interface_a = Column(String(128), default="")
    interface_b = Column(String(128), default="")
    protocol = Column(String(16), default="lldp")  # lldp | cdp
    hostname_a = Column(String(255), default="")
    hostname_b = Column(String(255), default="")
    created_at = Column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "source": self.endpoint_a,
            "target": self.endpoint_b,
            "source_interface": self.interface_a,
            "target_interface": self.interface_b,
            "protocol": self.protocol,
            "source_hostname": self.hostname_a,
            "target_hostname": self.hostname_b,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DeviceConfig(Base):
    """Stored device configuration backup (Sprint 9)."""

    __tablename__ = "device_configs"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    config_text = Column(Text, nullable=False)
    config_type = Column(String(32), default="running")  # running | startup | version
    collected_at = Column(DateTime, default=_utcnow, index=True)
    error = Column(Text, nullable=True)
    collected_by = Column(String(128), nullable=True)  # username that ran the collection

    device = relationship("Device", backref="configs")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "device_id": self.device_id,
            "ip": self.device.ip if self.device else "",
            "hostname": self.device.hostname if self.device else "",
            "config_type": self.config_type,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "error": self.error,
            "collected_by": self.collected_by,
            "config_text": self.config_text,
        }


class SiteMapping(Base):
    """A hostname-prefix → site rule used to attribute devices to sites (Sprint 13).

    Catalyst's network-device API returns null site fields for most devices, so
    site attribution falls back to a curated mapping of hostname prefixes
    (e.g. "AMTRCHIIL" or "MRSAMTRCH") to a site name. Devices whose hostname
    starts with a mapped prefix get the mapped site when the backfill runs.
    """

    __tablename__ = "site_mappings"

    id = Column(Integer, primary_key=True)
    prefix = Column(String(128), nullable=False, unique=True, index=True)
    site = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "prefix": self.prefix,
            "site": self.site,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class User(Base):
    """App user with an RBAC role: admin | operator | viewer."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), nullable=False, unique=True, index=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(16), nullable=False, default="viewer")  # admin | operator | viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ExecReport(Base):
    """An archived executive health report (Sprint: scheduled reporting)."""

    __tablename__ = "exec_reports"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=_utcnow, index=True)
    title = Column(String(255), default="")
    html = Column(Text, default="")           # self-contained printable HTML
    summary = Column(JSON, default=dict)      # raw exec_health_summary snapshot
    emailed = Column(Boolean, default=False)  # sent via SMTP (when configured)
    error = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "title": self.title,
            "emailed": self.emailed,
            "error": self.error,
        }


class InterfaceUtilization(Base):
    """Interface counter/rate samples for link utilization trends."""

    __tablename__ = "interface_utilization"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    if_index = Column(String(16), default="")
    if_name = Column(String(128), default="")
    if_speed = Column(String(32), default="")
    in_octets = Column(BigInteger, default=0)   # last raw ifHCInOctets
    out_octets = Column(BigInteger, default=0)  # last raw ifHCOutOctets
    in_rate = Column(Float, default=0.0)        # bits/sec derived from deltas
    out_rate = Column(Float, default=0.0)
    sampled_at = Column(DateTime, default=_utcnow, index=True)


class Notification(Base):
    """An alert/notification raised by the periodic health check."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=_utcnow, index=True)
    kind = Column(String(32), default="", index=True)   # flapping | down | spof
    severity = Column(String(16), default="info")        # info | warning | critical
    title = Column(String(255), default="")
    message = Column(Text, default="")
    device_ip = Column(String(45), default="", index=True)
    seen = Column(Boolean, default=False, index=True)
    emailed = Column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "kind": self.kind,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "device_ip": self.device_ip,
            "seen": self.seen,
            "emailed": self.emailed,
        }


class ApiToken(Base):
    """A long-lived API token (hashed at rest) for automation/scripting."""

    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), default="")
    token_hash = Column(String(64), unique=True, index=True)  # sha256 hex
    role = Column(String(16), default="operator")
    created_by = Column(String(64), default="")
    created_at = Column(DateTime, default=_utcnow)
    last_used_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "revoked": self.revoked,
        }


class HealthSnapshot(Base):
    """A periodic executive health score snapshot for trend charts."""

    __tablename__ = "health_snapshots"

    id = Column(Integer, primary_key=True)
    recorded_at = Column(DateTime, default=_utcnow, index=True)
    score = Column(Integer, default=0)
    state = Column(String(16), default="healthy")
    devices_up = Column(Integer, default=0)
    devices_down = Column(Integer, default=0)
    devices_flapping = Column(Integer, default=0)
    spof_count = Column(Integer, default=0)
    stale_devices = Column(Integer, default=0)
    config_coverage = Column(Float, default=0.0)
    site_coverage = Column(Float, default=0.0)
    interface_coverage = Column(Float, default=0.0)
    link_validation = Column(Float, default=0.0)
