const { execSync, exec } = require('child_process');
const net = require('net');
const os = require('os');

const PORT_SCAN_TIMEOUT = 800;
const PING_TIMEOUT = 1000;

const DEVICE_SIGNATURES = {
  router:     { ports: [80, 443, 161], keywords: ['router', 'gateway'] },
  switch:     { ports: [22, 23, 161, 80], keywords: ['switch'] },
  accesspoint:{ ports: [22, 80, 443], keywords: ['ap', 'access point', 'wireless'] },
  firewall:   { ports: [443, 8080, 8443], keywords: ['firewall', 'fortinet', 'paloalto', 'asa'] },
  server:     { ports: [22, 80, 443, 3389, 8080], keywords: ['server'] },
  pc:         { ports: [3389, 22], keywords: [] },
};

function getNetworkInterfaces() {
  const interfaces = os.networkInterfaces();
  const results = [];
  for (const [name, addrs] of Object.entries(interfaces)) {
    for (const addr of addrs) {
      if (addr.family === 'IPv4' && !addr.internal) {
        results.push({ name, address: addr.address, netmask: addr.netmask });
      }
    }
  }
  results.sort((a, b) => {
    const aPrivate = isPrivateIP(a.address) ? 0 : 1;
    const bPrivate = isPrivateIP(b.address) ? 0 : 1;
    return aPrivate - bPrivate;
  });
  return results;
}

function isPrivateIP(ip) {
  const parts = ip.split('.').map(Number);
  if (parts[0] === 10) return true;
  if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return true;
  if (parts[0] === 192 && parts[1] === 168) return true;
  return false;
}

function getLocalIP() {
  const ifaces = getNetworkInterfaces();
  const privateIface = ifaces.find(i => isPrivateIP(i.address));
  if (privateIface) return privateIface.address;
  return ifaces.length > 0 ? ifaces[0].address : '127.0.0.1';
}

function getSubnet() {
  const ifaces = getNetworkInterfaces();
  if (ifaces.length === 0) return '127.0.0.0';
  const iface = ifaces[0];
  const ipParts = iface.address.split('.').map(Number);
  const maskParts = iface.netmask.split('.').map(Number);
  const networkParts = ipParts.map((p, i) => p & maskParts[i]);
  return networkParts.join('.');
}

function getSubnetCIDR() {
  const ifaces = getNetworkInterfaces();
  if (ifaces.length === 0) return '127.0.0.0/8';
  const mask = ifaces[0].netmask;
  const bits = mask.split('.').reduce((acc, octet) => acc + (octet >>> 0).toString(2).split('1').length - 1, 0);
  return `${getSubnet()}/${bits}`;
}

function scanArpTable() {
  const devices = new Map();
  try {
    const       output = execSync('arp -an', { timeout: 5000, stdio: ['pipe', 'pipe', 'ignore'] }).toString();
    const regex = /\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-f:]+)\s+on\s+(\S+)/gi;
    let match;
    while ((match = regex.exec(output)) !== null) {
      const ip = match[1];
      const mac = match[2];
      const parts = ip.split('.').map(Number);
      if (mac.toLowerCase() === 'incomplete') continue;
      if (mac === 'ff:ff:ff:ff:ff:ff') continue;
      if (parts[0] === 169 && parts[1] === 254) continue;
      if (parts[0] >= 224) continue;
      if (parts[3] === 255) continue;
      devices.set(ip, { ip, mac, source: 'arp' });
    }
  } catch (e) {
    console.log('ARP table unavailable (will use ping sweep instead)');
  }
  return devices;
}

function pingHost(ip) {
  return new Promise(resolve => {
    const cmd = process.platform === 'win32'
      ? `ping -n 1 -w ${PING_TIMEOUT} ${ip}`
      : `ping -c 1 -W 2000 ${ip}`;
    exec(cmd, { timeout: 5000 }, (err) => {
      resolve(!err);
    });
  });
}

function pingSweep(subnet, onProgress) {
  return new Promise(async resolve => {
    const devices = new Map();
    const hosts = [];

    for (let i = 1; i <= 254; i++) {
      hosts.push(`${subnet}.${i}`);
    }

    const batchSize = 30;
    let completed = 0;

    for (let i = 0; i < hosts.length; i += batchSize) {
      const batch = hosts.slice(i, i + batchSize);
      const results = await Promise.all(batch.map(async ip => {
        const alive = await pingHost(ip);
        completed++;
        if (onProgress) onProgress(Math.round((completed / hosts.length) * 100));
        return { ip, alive };
      }));
      results.forEach(r => {
        if (r.alive) devices.set(r.ip, { ip: r.ip, source: 'ping' });
      });
    }

    resolve(devices);
  });
}

function scanPort(ip, port) {
  return new Promise(resolve => {
    const socket = new net.Socket();
    socket.setTimeout(PORT_SCAN_TIMEOUT);
    socket.on('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.on('timeout', () => {
      socket.destroy();
      resolve(false);
    });
    socket.on('error', () => {
      resolve(false);
    });
    socket.connect(port, ip);
  });
}

async function identifyDevice(ip) {
  const commonPorts = [22, 23, 80, 443, 161, 3389, 8080, 8443];
  const openPorts = [];

  const portResults = await Promise.all(
    commonPorts.map(async port => ({ port, open: await scanPort(ip, port) }))
  );

  portResults.filter(r => r.open).forEach(r => openPorts.push(r.port));

  let type = 'pc';
  let confidence = 0;

  for (const [deviceType, sig] of Object.entries(DEVICE_SIGNATURES)) {
    const matches = sig.ports.filter(p => openPorts.includes(p)).length;
    if (matches > confidence) {
      confidence = matches;
      type = deviceType;
    }
  }

  if (openPorts.includes(161)) {
    type = 'router';
    confidence = 3;
  }

  const isGateway = ip.endsWith('.1') || ip.endsWith('.254');
  if (isGateway && openPorts.length > 0) {
    type = 'router';
    confidence = 4;
  }

  let hostname = '';
  try {
    hostname = execSync(`nslookup ${ip}`, { timeout: 3000 }).toString();
    const nameMatch = hostname.match(/name\s*=\s*(.+)/i);
    if (nameMatch) hostname = nameMatch[1].trim();
    else hostname = '';
  } catch {
    hostname = '';
  }

  return { type, openPorts, hostname, confidence };
}

function lookupMacVendor(mac) {
  const prefixes = {
    '00:50:56': 'VMware',
    '08:00:27': 'VirtualBox',
    '52:54:00': 'QEMU/KVM',
    '00:0c:29': 'VMware',
    '00:1a:2b': 'Ayecom',
    '00:1b:21': 'Intel',
    '00:1e:65': 'Cisco',
    '00:24:d7': 'Cisco',
    '00:1a:a0': 'Cisco',
    'b8:27:eb': 'Raspberry Pi',
    'dc:a6:32': 'Raspberry Pi',
    'e4:5f:01': 'Raspberry Pi',
    'd8:3a:dd': 'Raspberry Pi',
    '28:cd:c1': 'Raspberry Pi',
    'ac:de:48': 'Private',
    'f8:1a:67': 'TP-Link',
    '14:cc:20': 'TP-Link',
    '50:c7:bf': 'TP-Link',
    '60:32:b1': 'TP-Link',
    'b0:4e:26': 'TP-Link',
    '30:b5:c2': 'TP-Link',
    '00:23:cd': 'Ubiquiti',
    '24:5a:4c': 'Ubiquiti',
    '18:e8:29': 'Ubiquiti',
    '44:d9:e7': 'Ubiquiti',
    '78:8a:20': 'Ubiquiti',
    'b4:fb:e4': 'Ubiquiti',
    '00:1d:d8': 'Cisco',
    'cc:16:7e': 'Cisco',
    'e0:2f:6d': 'Cisco',
    '68:99:cd': 'Cisco',
    'f8:7b:20': 'Cisco',
    'f4:4e:05': 'Cisco',
    'a0:3d:6f': 'Cisco',
    '00:0f:f7': 'Cisco',
    '00:26:0b': 'Cisco',
    'c8:b3:73': 'Cisco',
    '00:50:56': 'VMware',
    '74:40:be': 'LG',
    'ac:5f:3e': 'Samsung',
    '3c:5a:37': 'Samsung',
    '00:15:5d': 'Hyper-V',
  };

  if (!mac) return '';
  const prefix = mac.substring(0, 8).toLowerCase();
  return prefixes[prefix] || '';
}

async function discoverNetwork(options = {}) {
  const { onProgress, onDeviceFound } = options;
  const subnet = getSubnet();
  const localIP = getLocalIP();

  console.log(`Scanning subnet: ${subnet}.0/24`);
  console.log(`Local IP: ${localIP}`);

  if (onProgress) onProgress({ phase: 'arp', percent: 0 });

  let devices = scanArpTable();
  console.log(`ARP table: ${devices.size} devices found`);

  if (onProgress) onProgress({ phase: 'ping', percent: 0 });

  const pingDevices = await pingSweep(subnet, percent => {
    if (onProgress) onProgress({ phase: 'ping', percent });
  });
  console.log(`Ping sweep: ${pingDevices.size} hosts alive`);

  for (const [ip, data] of pingDevices) {
    if (!devices.has(ip)) devices.set(ip, data);
  }

  if (onProgress) onProgress({ phase: 'identify', percent: 0 });

  const topologyDevices = [];
  let identified = 0;

  for (const [ip, data] of devices) {
    identified++;
    if (onProgress) onProgress({
      phase: 'identify',
      percent: Math.round((identified / devices.size) * 100)
    });

    const info = await identifyDevice(ip);
    const vendor = lookupMacVendor(data.mac);

    const device = {
      ip,
      mac: data.mac || '',
      type: info.type,
      hostname: info.hostname || `${info.type}-${topologyDevices.length + 1}`,
      vendor,
      openPorts: info.openPorts,
      isLocal: ip === localIP,
    };

    topologyDevices.push(device);
    if (onDeviceFound) onDeviceFound(device);
  }

  topologyDevices.sort((a, b) => {
    const typeOrder = { router: 0, firewall: 1, switch: 2, accesspoint: 3, server: 4, pc: 5 };
    return (typeOrder[a.type] || 5) - (typeOrder[b.type] || 5);
  });

  const connections = buildConnections(topologyDevices);

  if (onProgress) onProgress({ phase: 'done', percent: 100 });

  return { devices: topologyDevices, connections };
}

function buildConnections(devices) {
  const connections = [];
  const routers = devices.filter(d => d.type === 'router');
  const firewalls = devices.filter(d => d.type === 'firewall');
  const switches = devices.filter(d => d.type === 'switch');
  const accessPoints = devices.filter(d => d.type === 'accesspoint');
  const servers = devices.filter(d => d.type === 'server');
  const pcs = devices.filter(d => d.type === 'pc');

  if (routers.length > 0 && firewalls.length > 0) {
    connections.push({ from: routers[0], to: firewalls[0], label: 'WAN' });
  }

  const core = routers.length > 0 ? routers[0] : (firewalls.length > 0 ? firewalls[0] : null);

  if (core) {
    switches.forEach(sw => {
      connections.push({ from: core, to: sw, label: 'Trunk' });
    });
    if (switches.length === 0 && servers.length > 0) {
      servers.forEach(s => connections.push({ from: core, to: s, label: 'LAN' }));
    }
  }

  if (switches.length > 0) {
    accessPoints.forEach(ap => {
      connections.push({ from: switches[0], to: ap, label: 'PoE' });
    });
    servers.forEach(s => {
      const sw = switches.length > 1 ? switches[switches.length - 1] : switches[0];
      connections.push({ from: sw, to: s, label: 'LAN' });
    });
    pcs.forEach(pc => {
      const sw = switches.length > 1 ? switches[0] : switches[0];
      connections.push({ from: sw, to: pc, label: 'LAN' });
    });
  }

  return connections.map(c => ({
    from: c.from.ip,
    to: c.to.ip,
    label: c.label
  }));
}

module.exports = {
  discoverNetwork,
  scanArpTable,
  pingSweep,
  identifyDevice,
  getLocalIP,
  getSubnet,
  getNetworkInterfaces
};
