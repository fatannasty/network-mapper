"""Integration: identify_host pulls SNMP data via the mock agent and classifies it."""

import pytest

import scanner
from tests.test_snmp import MockAgent


@pytest.fixture
def agent():
    mock = MockAgent()
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
