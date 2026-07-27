#!/usr/bin/env node

const { execSync, exec } = require('child_process');
const os = require('os');
const net = require('net');
const https = require('https');

const API_URL = process.env.API_URL || 'https://network-mapper-api.YOUR_SUBDOMAIN.workers.dev';
const LOCATION_ID = process.env.LOCATION_ID || 'default';
const LOCATION_NAME = process.env.LOCATION_NAME || LOCATION_ID;
const SCAN_INTERVAL = parseInt(process.env.SCAN_INTERVAL) || 300000;
const AGENT_ID = `agent-${LOCATION_ID}-${os.hostname()}`;

function log(msg) {
  console.log(`[${new Date().toISOString()}] [${LOCATION_ID}] ${msg}`);
}

function getSubnet() {
  const interfaces = os.networkInterfaces();
  for (const [name, addrs] of Object.entries(interfaces)) {
    for (const addr of addrs) {
      if (addr.family === 'IPv4' && !addr.internal) {
        const parts = addr.address.split('.').map(Number);
        const maskParts = addr.netmask.split('.').map(Number);
        const networkParts = parts.map((p, i) => p & maskParts[i]);
        const bits = maskParts.reduce((acc, o) => acc + (o >>> 0).toString(2).split('1').length - 1, 0);
        return { cidr: `${networkParts.join('.')}/${bits}`, ip: addr.address };
      }
    }
  }
  return { cidr: '192.168.0.0/24', ip: '127.0.0.1' };
}

function generateIPs(cidr) {
  const [baseIP, prefixStr] = cidr.split('/');
  const prefix = parseInt(prefixStr) || 24;
  const ipNum = baseIP.split('.').reduce((acc, o) => (acc << 8) + parseInt(o), 0);
  const hostBits = 32 - prefix;
  const networkAddr = ipNum & (0xFFFFFFFF << hostBits);
  const broadcastAddr = networkAddr | ((1 << hostBits) - 1);
  const ips = [];
  for (let i = networkAddr + 1; i < broadcastAddr; i++) {
    ips.push([(i >>> 24) & 0xFF, (i >>> 16) & 0xFF, (i >>> 8) & 0xFF, i & 0xFF].join('.'));
  }
  return ips;
}

function pingHost(ip) {
  return new Promise(resolve => {
    const cmd = process.platform === 'win32'
      ? `ping -n 1 -w 1000 ${ip}`
      : `ping -c 1 -W 1000 ${ip}`;
    exec(cmd, { timeout: 2000 }, (err) => resolve(!err));
  });
}

function scanArpTable() {
  const devices = new Map();
  try {
    const cmd = process.platform === 'darwin' ? 'arp -an' : (process.platform === 'win32' ? 'arp -a' : 'arp -an');
    const output = execSync(cmd, { timeout: 10000, stdio: ['pipe', 'pipe', 'ignore'] }).toString();
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
  } catch (e) {}
  return devices;
}

function scanPort(ip, port) {
  return new Promise(resolve => {
    const socket = new net.Socket();
    socket.setTimeout(800);
    socket.on('connect', () => { socket.destroy(); resolve(true); });
    socket.on('timeout', () => { socket.destroy(); resolve(false); });
    socket.on('error', () => resolve(false));
    socket.connect(port, ip);
  });
}

async function identifyDevice(ip) {
  const ports = [22, 23, 80, 443, 161, 3389, 8080, 8443];
  const results = await Promise.all(ports.map(async p => ({ port: p, open: await scanPort(ip, p) })));
  const openPorts = results.filter(r => r.open).map(r => r.port);

  let type = 'pc';
  if (openPorts.includes(161) || (ip.endsWith('.1') && openPorts.length > 0)) type = 'router';
  else if (openPorts.includes(443) && openPorts.includes(8080)) type = 'firewall';
  else if (openPorts.includes(22) && openPorts.includes(80)) type = 'switch';
  else if (openPorts.includes(22) && openPorts.length >= 3) type = 'server';

  let hostname = '';
  try {
    const out = execSync(`nslookup ${ip}`, { timeout: 3000 }).toString();
    const m = out.match(/name\s*=\s*(.+)/i);
    if (m) hostname = m[1].trim();
  } catch {}

  return { type, openPorts, hostname };
}

function postAPI(path, data) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, API_URL);
    const body = JSON.stringify(data);
    const req = https.request({
      hostname: url.hostname,
      path: url.pathname,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
    }, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch { resolve({}); } });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

async function runScan() {
  log('Starting scan...');
  const { cidr, ip } = getSubnet();
  log(`Scanning ${cidr} (local IP: ${ip})`);

  const arpDevices = scanArpTable();
  log(`ARP: ${arpDevices.size} devices`);

  const hosts = generateIPs(cidr);
  log(`Ping sweep: ${hosts.length} hosts`);
  const batchSize = 50;
  const aliveDevices = new Map();

  for (let i = 0; i < hosts.length; i += batchSize) {
    const batch = hosts.slice(i, i + batchSize);
    const results = await Promise.all(batch.map(async h => ({ ip: h, alive: await pingHost(h) })));
    results.filter(r => r.alive).forEach(r => aliveDevices.set(r.ip, { ip: r.ip, source: 'ping' }));
    if ((i / batchSize) % 10 === 0) log(`Progress: ${Math.min(i + batchSize, hosts.length)}/${hosts.length}`);
  }
  log(`Alive: ${aliveDevices.size} hosts`);

  for (const [ip, data] of arpDevices) {
    if (!aliveDevices.has(ip)) aliveDevices.set(ip, data);
  }

  const devices = [];
  let idx = 0;
  for (const [ip, data] of aliveDevices) {
    idx++;
    if (idx % 20 === 0) log(`Identifying: ${idx}/${aliveDevices.size}`);
    const info = await identifyDevice(ip);
    devices.push({
      ip,
      mac: data.mac || '',
      type: info.type,
      hostname: info.hostname || `${info.type}-${devices.length + 1}`,
      openPorts: info.openPorts,
    });
  }
  log(`Scan complete: ${devices.length} devices found`);

  try {
    await postAPI('/api/scan', {
      locationId: LOCATION_ID,
      locationName: LOCATION_NAME,
      devices,
      connections: [],
      subnet: cidr,
      scannedAt: new Date().toISOString(),
    });
    log('Results pushed to API');
  } catch (e) {
    log(`Push failed: ${e.message}`);
  }
}

async function main() {
  log(`Agent starting (ID: ${AGENT_ID})`);
  log(`API: ${API_URL}`);
  log(`Scan interval: ${SCAN_INTERVAL / 1000}s`);

  try {
    await postAPI('/api/agent/register', {
      agentId: AGENT_ID,
      locationId: LOCATION_ID,
      locationName: LOCATION_NAME,
      ip: getSubnet().ip,
    });
    log('Registered with API');
  } catch (e) {
    log(`Registration failed: ${e.message}`);
  }

  await runScan();

  if (SCAN_INTERVAL > 0) {
    setInterval(async () => {
      try {
        await postAPI('/api/agent/heartbeat', { agentId: AGENT_ID });
      } catch {}
      await runScan();
    }, SCAN_INTERVAL);
  }
}

main().catch(err => {
  log(`Fatal error: ${err.message}`);
  process.exit(1);
});
