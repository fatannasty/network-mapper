"""SQLAlchemy ORM models: Devices, ScanJobs, Credentials, Sites."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
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

    last_scan_id = Column(String(32), ForeignKey("scan_jobs.id"), nullable=True)
    first_seen = Column(DateTime, default=_utcnow)
    last_seen = Column(DateTime, default=_utcnow, onupdate=_utcnow)

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
            "last_scan_id": self.last_scan_id,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


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
    scanned_hosts = Column(Integer, default=0)
    alive_hosts = Column(Integer, default=0)
    device_count = Column(Integer, default=0)
    snmp_identified = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=_utcnow)
    finished_at = Column(DateTime, nullable=True)

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
