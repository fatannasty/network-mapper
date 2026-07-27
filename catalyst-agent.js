#!/usr/bin/env node

const https = require('https');
const http = require('http');

// ─── Configuration (set via environment variables) ───

const CAT_CENTER_URL = process.env.CAT_CENTER_URL || 'https://sandboxdnac.cisco.com';
const CAT_CENTER_USER = process.env.CAT_CENTER_USER || 'devnetcat';
const CAT_CENTER_PASS = process.env.CAT_CENTER_PASS || 'Cisco123!';
const API_URL = process.env.API_URL || 'https://network-mapper-api.fatannasty.workers.dev';
const SCAN_INTERVAL = parseInt(process.env.SCAN_INTERVAL) || 300000;
const LOCATION_PREFIX = process.env.LOCATION_PREFIX || '';

function log(msg) {
  console.log(`[${new Date().toISOString()}] ${msg}`);
}

// ─── HTTP Client ───

function httpRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const isHttps = parsed.protocol === 'https:';
    const client = isHttps ? https : http;

    const reqOptions = {
      hostname: parsed.hostname,
      port: parsed.port || (isHttps ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method: options.method || 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      rejectUnauthorized: false,
    };

    const req = client.request(reqOptions, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(data) });
        } catch {
          resolve({ status: res.statusCode, data });
        }
      });
    });

    req.on('error', reject);
    req.setTimeout(30000, () => { req.destroy(); reject(new Error('Request timeout')); });

    if (options.body) req.write(JSON.stringify(options.body));
    req.end();
  });
}

// ─── Catalyst Center Authentication ───

let authToken = null;
let tokenExpiry = 0;

async function authenticate() {
  if (authToken && Date.now() < tokenExpiry) return authToken;

  log('Authenticating with Catalyst Center...');
  const url = `${CAT_CENTER_URL}/dna/system/api/v1/auth/token`;
  const auth = Buffer.from(`${CAT_CENTER_USER}:${CAT_CENTER_PASS}`).toString('base64');

  const res = await httpRequest(url, {
    method: 'POST',
    headers: { 'Authorization': `Basic ${auth}` },
  });

  if (res.status !== 200 || !res.data?.Token) {
    throw new Error(`Authentication failed: ${res.status} - ${JSON.stringify(res.data)}`);
  }

  authToken = res.data.Token;
  tokenExpiry = Date.now() + (res.data.validSeconds || 3600) * 1000 - 60000;
  log('Authenticated successfully');
  return authToken;
}

async function apiGet(path) {
  const token = await authenticate();
  const url = `${CAT_CENTER_URL}${path}`;
  const res = await httpRequest(url, {
    headers: { 'X-Auth-Token': token },
  });

  if (res.status !== 200) {
    throw new Error(`API error ${res.status}: ${JSON.stringify(res.data)}`);
  }

  return res.data;
}

async function apiGetAll(path) {
  const token = await authenticate();
  let allRecords = [];
  let offset = 0;
  const limit = 500;

  while (true) {
    const separator = path.includes('?') ? '&' : '?';
    const url = `${CAT_CENTER_URL}${path}${separator}offset=${offset}&limit=${limit}`;
    const res = await httpRequest(url, {
      headers: { 'X-Auth-Token': token },
    });

    if (res.status !== 200) break;

    const records = res.data?.response || res.data?.devices || res.data || [];
    if (Array.isArray(records)) {
      allRecords = allRecords.concat(records);
      if (records.length < limit) break;
      offset += limit;
    } else {
      allRecords.push(res.data);
      break;
    }
  }

  return allRecords;
}

// ─── Catalyst Center Data Fetching ───

async function getDevices() {
  log('Fetching device inventory...');
  const devices = await apiGetAll('/dna/intent/api/v1/network-device');
  log(`Found ${devices.length} devices`);
  return devices;
}

async function getInterfaces(deviceId) {
  try {
    const res = await apiGet(`/dna/intent/api/v1/interface?deviceId=${deviceId}`);
    return res.response || res || [];
  } catch {
    return [];
  }
}

async function getTopology() {
  log('Fetching network topology...');
  try {
    const res = await apiGet('/dna/intent/api/v1/topology/network-topology?searchBy=&classEntity=capability');
    return res.response?.topology || [];
  } catch (e) {
    log(`Topology fetch failed: ${e.message}`);
    return [];
  }
}

async function getSites() {
  log('Fetching site hierarchy...');
  try {
    const res = await apiGet('/dna/intent/api/v1/site');
    return res.response || [];
  } catch (e) {
    log(`Site fetch failed: ${e.message}`);
    return [];
  }
}

async function getSiteDevices(siteId) {
  try {
    const res = await apiGet(`/dna/intent/api/v1/site/${siteId}/member/device`);
    return res.response || [];
  } catch {
    return [];
  }
}

async function getDeviceHealth() {
  try {
    const res = await apiGet('/dna/intent/api/v1/device-health');
    return res.response || [];
  } catch {
    return [];
  }
}

// ─── Data Transformation ───

function mapDeviceType(catCenter) {
  const family = (catCenter.family || '').toLowerCase();
  const platform = (catCenter.platformId || '').toLowerCase();

  if (family.includes('router') || platform.includes('isr') || platform.includes('csr')) return 'router';
  if (family.includes('switch') || platform.includes('catalyst')) return 'switch';
  if (family.includes('wireless') || platform.includes('wlc') || platform.includes('ap')) return 'accesspoint';
  if (family.includes('firewall') || platform.includes('asa') || platform.includes('ftd')) return 'firewall';
  if (family.includes('server')) return 'server';

  if (platform.includes('nexus')) return 'switch';
  if (platform.includes('meraki')) return 'switch';

  return 'pc';
}

function mapDeviceName(device) {
  if (device.name) return device.name;
  if (device.hostname) return device.hostname;
  if (device.managementIpAddress) return device.managementIpAddress;
  return `Device-${device.id?.substring(0, 8) || 'unknown'}`;
}

function getOpenPorts(device) {
  const ports = [];
  if (device.snmpReachability !== 'Unreachable') ports.push(161);
  if (device.telnetReachability !== 'Unreachable') ports.push(23);
  if (device.sshReachability !== 'Unreachable') ports.push(22);
  if (device.httpReachability !== 'Unreachable') ports.push(80);
  if (device.httpsReachability !== 'Unreachable') ports.push(443);
  return ports;
}

function buildConnections(devices, topology) {
  const connections = [];

  if (topology && topology.length > 0) {
    for (const topo of topology) {
      const sourceId = topo.source?.neighbor?.deviceId || topo.source?.device?.id;
      const targetId = topo.target?.neighbor?.deviceId || topo.target?.device?.id;

      if (sourceId && targetId && sourceId !== targetId) {
        const existing = connections.find(c =>
          (c.from === sourceId && c.to === targetId) ||
          (c.from === targetId && c.to === sourceId)
        );
        if (!existing) {
          connections.push({
            from: sourceId,
            to: targetId,
            label: topo.linkInformation?.captureName || '',
            vlanUp: '',
            vlanDown: '',
          });
        }
      }
    }
  }

  if (connections.length === 0) {
    const switches = devices.filter(d => mapDeviceType(d) === 'switch');
    const routers = devices.filter(d => mapDeviceType(d) === 'router');
    const aps = devices.filter(d => mapDeviceType(d) === 'accesspoint');
    const servers = devices.filter(d => mapDeviceType(d) === 'server');
    const firewalls = devices.filter(d => mapDeviceType(d) === 'firewall');
    const pcs = devices.filter(d => mapDeviceType(d) === 'pc');

    if (routers.length > 0 && firewalls.length > 0) {
      connections.push({ from: routers[0].id, to: firewalls[0].id, label: 'WAN', vlanUp: '', vlanDown: '' });
    }

    const core = routers[0] || firewalls[0];
    if (core) {
      switches.forEach(sw => {
        connections.push({ from: core.id, to: sw.id, label: 'Trunk', vlanUp: '', vlanDown: '' });
      });
    }

    if (switches.length > 0) {
      aps.forEach(ap => connections.push({ from: switches[0].id, to: ap.id, label: 'PoE', vlanUp: '', vlanDown: '' }));
      servers.forEach(s => {
        const sw = switches.length > 1 ? switches[switches.length - 1] : switches[0];
        connections.push({ from: sw.id, to: s.id, label: 'LAN', vlanUp: '', vlanDown: '' });
      });
      pcs.forEach(pc => {
        connections.push({ from: switches[0].id, to: pc.id, label: 'LAN', vlanUp: '', vlanDown: '' });
      });
    }
  }

  return connections;
}

// ─── API Push ───

function postAPI(path, data) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, API_URL);
    const body = JSON.stringify(data);
    const reqOptions = {
      hostname: url.hostname,
      path: url.pathname,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
      rejectUnauthorized: false,
    };

    const req = https.request(reqOptions, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch { resolve({}); } });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

// ─── Main Logic ───

async function scanLocation(siteId, siteName, devices, connections) {
  const locationId = LOCATION_PREFIX ? `${LOCATION_PREFIX}-${siteId}` : siteId;
  const mappedDevices = devices.map(d => ({
    ip: d.managementIpAddress || '',
    mac: d.macAddress || '',
    type: mapDeviceType(d),
    hostname: mapDeviceName(d),
    openPorts: getOpenPorts(d),
    vendor: d.serialNumber || '',
    platform: d.platformId || '',
    softwareVersion: d.softwareVersion || '',
    upTime: d.upTime || '',
    reachability: d.reachability || '',
  }));

  log(`Pushing ${locationId}: ${mappedDevices.length} devices, ${connections.length} connections`);

  await postAPI('/api/scan', {
    locationId,
    locationName: siteName,
    devices: mappedDevices,
    connections,
    subnet: 'catalyst-center',
    scannedAt: new Date().toISOString(),
  });
}

async function runScan() {
  log('Starting Catalyst Center scan...');

  try {
    const [devices, sites, topology] = await Promise.all([
      getDevices(),
      getSites(),
      getTopology(),
    ]);

    log(`Devices: ${devices.length}, Sites: ${sites.length}, Topology links: ${topology.length}`);

    if (sites.length > 0) {
      for (const site of sites) {
        const siteId = site.id || site.siteId;
        const siteName = site.name || site.siteNameHierarchy || `Site-${siteId}`;
        log(`Processing site: ${siteName}`);

        const siteDevices = await getSiteDevices(siteId);
        if (siteDevices.length > 0) {
          const deviceIds = new Set(siteDevices.map(d => d.id));
          const siteDeviceData = devices.filter(d => deviceIds.has(d.id));
          const siteTopology = topology.filter(t => {
            const src = t.source?.neighbor?.deviceId || t.source?.device?.id;
            const tgt = t.target?.neighbor?.deviceId || t.target?.device?.id;
            return deviceIds.has(src) || deviceIds.has(tgt);
          });

          await scanLocation(siteId, siteName, siteDeviceData, buildConnections(siteDeviceData, siteTopology));
        }
      }
    } else {
      log('No sites found - pushing all devices as single location');
      await scanLocation('catalyst-center', 'Catalyst Center', devices, buildConnections(devices, topology));
    }

    log('Scan complete!');
  } catch (e) {
    log(`Scan failed: ${e.message}`);
    throw e;
  }
}

async function testConnection() {
  log('Testing connection to Catalyst Center...');
  try {
    await authenticate();
    const devices = await getDevices();
    log(`SUCCESS: Connected! Found ${devices.length} devices`);

    const sites = await getSites();
    log(`Sites: ${sites.length}`);

    const topology = await getTopology();
    log(`Topology links: ${topology.length}`);

    const health = await getDeviceHealth();
    log(`Device health entries: ${health.length}`);

    return true;
  } catch (e) {
    log(`FAILED: ${e.message}`);
    return false;
  }
}

// ─── Entry Point ───

async function main() {
  log('Network Mapper - Catalyst Center Agent');
  log(`Cat Center: ${CAT_CENTER_URL}`);
  log(`API: ${API_URL}`);
  log(`Interval: ${SCAN_INTERVAL / 1000}s`);

  if (process.argv.includes('--test')) {
    await testConnection();
    process.exit(0);
  }

  try {
    await runScan();
  } catch (e) {
    log(`Initial scan failed: ${e.message}`);
  }

  if (SCAN_INTERVAL > 0) {
    log(`Scheduling scans every ${SCAN_INTERVAL / 1000}s`);
    setInterval(async () => {
      try { await runScan(); } catch (e) { log(`Scan error: ${e.message}`); }
    }, SCAN_INTERVAL);
  }
}

main().catch(err => {
  log(`Fatal: ${err.message}`);
  process.exit(1);
});
