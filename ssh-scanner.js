const { execSync } = require('child_process');
const net = require('net');

const SSH_TIMEOUT = 15000;

function sshCommand(host, user, pass, command) {
  return new Promise((resolve, reject) => {
    const sshpassPath = process.platform === 'darwin' ? `${process.env.HOME}/bin/sshpass` : 'sshpass';
    const sshCmd = `${sshpassPath} -p '${pass}' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 ${user}@${host} "${command}"`;
    exec(sshCmd, { timeout: SSH_TIMEOUT }, (err, stdout, stderr) => {
      if (err) reject(new Error(stderr || err.message));
      else resolve(stdout);
    });
  });
}

function parseCdpNeighbors(output) {
  const devices = [];
  const lines = output.split('\n');
  let currentDevice = null;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    const cdpMatch = trimmed.match(/^(\S+)\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(\S+)\s*/);
    if (cdpMatch) {
      devices.push({
        hostname: cdpMatch[1],
        platform: cdpMatch[2],
        port: cdpMatch[3],
      });
      continue;
    }

    const deviceMatch = trimmed.match(/^Device ID:\s*(.+)/);
    if (deviceMatch) {
      currentDevice = { hostname: deviceMatch[1].trim() };
      continue;
    }

    const ipMatch = trimmed.match(/^IP address:\s*(.+)/);
    if (ipMatch && currentDevice) {
      currentDevice.ip = ipMatch[1].trim();
      continue;
    }

    const platformMatch = trimmed.match(/^Platform:\s*(.+)/);
    if (platformMatch && currentDevice) {
      currentDevice.platform = platformMatch[1].trim();
      continue;
    }

    const portMatch = trimmed.match(/^Interface:\s*(.+),\s*Port ID:\s*(.+)/);
    if (portMatch && currentDevice) {
      currentDevice.localPort = portMatch[1].trim();
      currentDevice.remotePort = portMatch[2].trim();
      devices.push(currentDevice);
      currentDevice = null;
      continue;
    }
  }

  return devices;
}

function parseMacTable(output) {
  const entries = [];
  const lines = output.split('\n');

  for (const line of lines) {
    const match = line.match(/(\d+)\s+([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+(DYNAMIC|STATIC)\s+(\S+)/i);
    if (match) {
      entries.push({
        vlan: match[1],
        mac: match[2],
        type: match[3],
        port: match[4],
      });
    }
  }

  return entries;
}

function parseArpTable(output) {
  const entries = [];
  const lines = output.split('\n');

  for (const line of lines) {
    const match = line.match(/(\d+\.\d+\.\d+\.\d+)\s+\d+\s+([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+(\S+)/i);
    if (match) {
      entries.push({
        ip: match[1],
        mac: match[2],
        port: match[3],
      });
    }
  }

  return entries;
}

function parseInterfaces(output) {
  const interfaces = [];
  const lines = output.split('\n');
  let current = null;

  for (const line of lines) {
    const trimmed = line.trim();

    const ifMatch = trimmed.match(/^(\S+\/\S+\/\S+)\s/);
    if (ifMatch) {
      if (current) interfaces.push(current);
      current = { name: ifMatch[1], status: 'unknown', vlan: '', description: '' };
      continue;
    }

    if (current) {
      if (trimmed.includes('up')) current.status = 'up';
      if (trimmed.includes('down')) current.status = 'down';

      const descMatch = trimmed.match(/^Description:\s*(.+)/i);
      if (descMatch) current.description = descMatch[1].trim();

      const vlanMatch = trimmed.match(/access\s+vlan\s+(\d+)/i);
      if (vlanMatch) current.vlan = vlanMatch[1];
    }
  }

  if (current) interfaces.push(current);
  return interfaces;
}

function parseVlans(output) {
  const vlans = [];
  const lines = output.split('\n');

  for (const line of lines) {
    const match = line.match(/(\d+)\s+(\S+)\s+(active|suspend)/i);
    if (match) {
      vlans.push({
        id: match[1],
        name: match[2],
        status: match[3],
      });
    }
  }

  return vlans;
}

function parseVersion(output) {
  const match = output.match(/Cisco IOS.*?Version\s+(\S+)/i);
  return match ? match[1] : '';
}

function parseHostname(output) {
  return output.trim().split('\n').pop()?.trim() || '';
}

async function scanCoreSwitch(config) {
  const { host, user, pass, location } = config;

  console.log(`Connecting to ${user}@${host}...`);

  const results = {
    hostname: '',
    ip: host,
    location: location || '',
    model: '',
    version: '',
    interfaces: [],
    cdpNeighbors: [],
    macTable: [],
    arpTable: [],
    vlans: [],
    devices: [],
    connections: [],
  };

  try {
    const hostnameOut = await sshCommand(host, user, pass, 'show hostname');
    results.hostname = parseHostname(hostnameOut);
    console.log(`Hostname: ${results.hostname}`);

    const versionOut = await sshCommand(host, user, pass, 'show version | include IOS');
    results.version = parseVersion(versionOut);
    console.log(`Version: ${results.version}`);

    const modelOut = await sshCommand(host, user, pass, 'show version | include Model');
    results.model = modelOut.trim().split('\n').pop()?.trim() || '';
    console.log(`Model: ${results.model}`);

    try {
      const cdpOut = await sshCommand(host, user, pass, 'show cdp neighbor detail');
      results.cdpNeighbors = parseCdpNeighbors(cdpOut);
      console.log(`CDP neighbors: ${results.cdpNeighbors.length}`);
    } catch { console.log('CDP not available'); }

    try {
      const macOut = await sshCommand(host, user, pass, 'show mac address-table dynamic');
      results.macTable = parseMacTable(macOut);
      console.log(`MAC entries: ${results.macTable.length}`);
    } catch { console.log('MAC table not available'); }

    try {
      const arpOut = await sshCommand(host, user, pass, 'show arp');
      results.arpTable = parseArpTable(arpOut);
      console.log(`ARP entries: ${results.arpTable.length}`);
    } catch { console.log('ARP table not available'); }

    try {
      const intfOut = await sshCommand(host, user, pass, 'show ip interface brief');
      results.interfaces = parseInterfaces(intfOut);
      console.log(`Interfaces: ${results.interfaces.length}`);
    } catch { console.log('Interfaces not available'); }

    try {
      const vlanOut = await sshCommand(host, user, pass, 'show vlan brief');
      results.vlans = parseVlans(vlanOut);
      console.log(`VLANs: ${results.vlans.length}`);
    } catch { console.log('VLANs not available'); }

    results.devices.push({
      ip: host,
      mac: '',
      type: 'core-switch',
      hostname: results.hostname || host,
      openPorts: [22, 161],
      vendor: 'Cisco',
      model: results.model,
      location: location || '',
    });

    for (const neighbor of results.cdpNeighbors) {
      const arpEntry = results.arpTable.find(a => a.ip === neighbor.ip);
      results.devices.push({
        ip: neighbor.ip || '',
        mac: arpEntry?.mac || '',
        type: mapPlatformToType(neighbor.platform),
        hostname: neighbor.hostname,
        openPorts: [22, 161],
        vendor: 'Cisco',
        model: neighbor.platform || '',
        location: location || '',
      });

      if (neighbor.ip && neighbor.localPort && neighbor.remotePort) {
        results.connections.push({
          from: host,
          to: neighbor.ip,
          label: neighbor.platform || '',
          vlanUp: '',
          vlanDown: '',
          cableType: 'unknown',
          portA: neighbor.localPort,
          portB: neighbor.remotePort,
        });
      }
    }

    console.log(`Total devices discovered: ${results.devices.length}`);
    console.log(`Total connections: ${results.connections.length}`);

  } catch (e) {
    console.error(`SSH error: ${e.message}`);
    throw e;
  }

  return results;
}

function mapPlatformToType(platform) {
  if (!platform) return 'pc';
  const p = platform.toLowerCase();
  if (p.includes('switch') || p.includes('catalyst')) return 'access-switch';
  if (p.includes('router') || p.includes('isr')) return 'router';
  if (p.includes('wireless') || p.includes('wlc') || p.includes('ap')) return 'accesspoint';
  if (p.includes('asa') || p.includes('firewall') || p.includes('ftd')) return 'firewall';
  if (p.includes('nexus')) return 'core-switch';
  return 'pc';
}

module.exports = { scanCoreSwitch, parseCdpNeighbors, parseMacTable, parseArpTable };
