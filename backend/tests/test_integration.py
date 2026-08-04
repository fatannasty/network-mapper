"""Integration: identify_host pulls SNMP data via the mock agent and classifies it."""

import pytest

import scanner
from tests.test_snmp import MockAgent
from tests.test_snmpv3 import MockV3Agent, AUTH_PW, PRIV_PW


@pytest.fixture
def agent():
    mock = MockAgent()
    yield mock
    mock.close()


@pytest.fixture
def v3agent():
    mock = MockV3Agent()
    yield mock
    mock.close()


def test_identify_host_snmp_classification(agent):
    device = scanner.identify_host("127.0.0.1", communities=["public"], snmp_port=agent.port)
    assert agent.port in device["open_ports"]
    assert device["hostname"] == "core-sw1"
    assert device["vendor"] == "Cisco"
    assert device["device_type"] == "switch"
    assert device["confidence"] == 4
    assert "C9300L" in device["model"]


def test_identify_host_wrong_community(agent):
    device = scanner.identify_host("127.0.0.1", communities=["nope"], snmp_port=agent.port)
    assert device["vendor"] == ""
    assert device["confidence"] == 0


def test_identify_host_v3_with_interfaces(v3agent):
    params = {
        "username": "testuser",
        "auth_protocol": "sha",
        "auth_password": AUTH_PW,
        "privacy_protocol": "aes",
        "privacy_password": PRIV_PW,
    }
    device = scanner.identify_host("127.0.0.1", communities=[], snmp_port=v3agent.port, snmpv3=params)
    assert device["vendor"] == "Net-SNMP"
    assert device["snmp_community"] == ""
    assert len(device["interfaces"]) == 2
    descrs = {i["ifDescr"] for i in device["interfaces"]}
    assert descrs == {"eth0", "lo"}
