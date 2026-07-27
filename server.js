const express = require('express');
const http = require('http');
const https = require('https');
const { WebSocketServer } = require('ws');
const path = require('path');
const scanner = require('./scanner');

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

const PORT = process.env.PORT || 7777;

app.use(express.static(__dirname));
app.use(express.json());

app.get('/api/info', (req, res) => {
  const ifaces = scanner.getNetworkInterfaces();
  res.json({
    localIP: scanner.getLocalIP(),
    subnet: scanner.getSubnet(),
    suggestedCIDR: `${scanner.getSubnet()}.0/24`,
    interfaces: ifaces,
    currentInterface: ifaces[0] ? ifaces[0].name : 'unknown',
  });
});

app.post('/api/scan', async (req, res) => {
  try {
    const cidr = req.body.cidr || null;
    console.log(`Starting network scan${cidr ? ' for ' + cidr : ''}...`);
    const result = await scanner.discoverNetwork({
      cidr,
      onDeviceFound: (device) => {
        broadcast({ type: 'device-found', device });
      }
    });
    console.log(`Scan complete: ${result.devices.length} devices found`);
    res.json(result);
  } catch (err) {
    console.error('Scan error:', err);
    res.status(500).json({ error: err.message });
  }
});

app.get('/api/arp', (req, res) => {
  try {
    const devices = scanner.scanArpTable();
    res.json({ devices: Array.from(devices.values()) });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

function catcHttpRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const client = parsed.protocol === 'https:' ? https : http;
    const reqOptions = {
      hostname: parsed.hostname,
      port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method: options.method || 'GET',
      headers: { 'Content-Type': 'application/json', ...options.headers },
      rejectUnauthorized: false,
    };
    const req = client.request(reqOptions, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => { try { resolve({ status: res.statusCode, data: JSON.parse(data) }); } catch { resolve({ status: res.statusCode, data }); } });
    });
    req.on('error', reject);
    req.setTimeout(30000, () => { req.destroy(); reject(new Error('Timeout')); });
    if (options.body) req.write(JSON.stringify(options.body));
    req.end();
  });
}

app.post('/api/catc/test', async (req, res) => {
  try {
    const { url, user, pass } = req.body;
    const auth = Buffer.from(`${user}:${pass}`).toString('base64');
    const tokenRes = await catcHttpRequest(`${url}/dna/system/api/v1/auth/token`, {
      method: 'POST',
      headers: { 'Authorization': `Basic ${auth}` },
    });
    if (tokenRes.status !== 200 || !tokenRes.data?.Token) {
      return res.json({ success: false, error: `Auth failed: ${tokenRes.status}` });
    }
    const deviceRes = await catcHttpRequest(`${url}/dna/intent/api/v1/network-device`, {
      headers: { 'X-Auth-Token': tokenRes.data.Token },
    });
    const count = Array.isArray(deviceRes.data?.response) ? deviceRes.data.response.length : 0;
    res.json({ success: true, deviceCount: count });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

app.post('/api/catc/scan', async (req, res) => {
  try {
    const { url, user, pass } = req.body;
    const WORKER_API = 'https://network-mapper-api.fatannasty.workers.dev';
    const auth = Buffer.from(`${user}:${pass}`).toString('base64');
    const tokenRes = await catcHttpRequest(`${url}/dna/system/api/v1/auth/token`, {
      method: 'POST',
      headers: { 'Authorization': `Basic ${auth}` },
    });
    if (tokenRes.status !== 200 || !tokenRes.data?.Token) {
      return res.json({ success: false, error: 'Auth failed' });
    }
    const token = tokenRes.data.Token;

    const deviceRes = await catcHttpRequest(`${url}/dna/intent/api/v1/network-device`, {
      headers: { 'X-Auth-Token': token },
    });
    const devices = deviceRes.data?.response || [];

    let sites = [];
    try {
      const siteRes = await catcHttpRequest(`${url}/dna/intent/api/v1/site`, {
        headers: { 'X-Auth-Token': token },
      });
      sites = siteRes.data?.response || [];
    } catch {}

    let topology = [];
    try {
      const topoRes = await catcHttpRequest(`${url}/dna/intent/api/v1/topology/network-topology`, {
        headers: { 'X-Auth-Token': token },
      });
      topology = topoRes.data?.response?.topology || [];
    } catch {}

    const mapType = (d) => {
      const f = (d.family || '').toLowerCase();
      const p = (d.platformId || '').toLowerCase();
      if (f.includes('router') || p.includes('isr')) return 'router';
      if (f.includes('switch') || p.includes('catalyst') || p.includes('nexus')) return 'switch';
      if (f.includes('wireless') || p.includes('wlc') || p.includes('ap')) return 'accesspoint';
      if (f.includes('firewall') || p.includes('asa') || p.includes('ftd')) return 'firewall';
      return 'pc';
    };

    const postToWorker = async (locId, locName, devs) => {
      const mapped = devs.map(d => ({
        ip: d.managementIpAddress || '',
        mac: d.macAddress || '',
        type: mapType(d),
        hostname: d.name || d.hostname || d.managementIpAddress || 'Unknown',
        openPorts: [
          d.snmpReachability !== 'Unreachable' ? 161 : null,
          d.sshReachability !== 'Unreachable' ? 22 : null,
          d.httpsReachability !== 'Unreachable' ? 443 : null,
        ].filter(Boolean),
        vendor: d.platformId || '',
      }));
      await catcHttpRequest(`${WORKER_API}/api/scan`, {
        method: 'POST',
        body: { locationId: locId, locationName: locName, devices: mapped, connections: [], subnet: 'catalyst-center', scannedAt: new Date().toISOString() },
      });
    };

    let locationCount = 0;
    if (sites.length > 0) {
      for (const site of sites) {
        const siteId = site.id || site.siteId;
        const siteName = site.name || site.siteNameHierarchy || `Site-${siteId}`;
        try {
          const memberRes = await catcHttpRequest(`${url}/dna/intent/api/v1/site/${siteId}/member/device`, {
            headers: { 'X-Auth-Token': token },
          });
          const memberIds = new Set((memberRes.data?.response || []).map(d => d.id));
          if (memberIds.size > 0) {
            const siteDevices = devices.filter(d => memberIds.has(d.id));
            await postToWorker(siteId, siteName, siteDevices);
            locationCount++;
          }
        } catch {}
      }
    }

    if (locationCount === 0) {
      await postToWorker('catalyst-center', 'Catalyst Center', devices);
      locationCount = 1;
    }

    res.json({ success: true, deviceCount: devices.length, locationCount });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

wss.on('connection', (ws) => {
  console.log('WebSocket client connected');
  ws.on('close', () => console.log('WebSocket client disconnected'));
});

function broadcast(data) {
  const msg = JSON.stringify(data);
  wss.clients.forEach(client => {
    if (client.readyState === 1) client.send(msg);
  });
}

server.listen(PORT, () => {
  const localIP = scanner.getLocalIP();
  const subnet = scanner.getSubnet();
  const ifaces = scanner.getNetworkInterfaces();
  console.log(`\n  Network Topology Mapper`);
  console.log(`  ───────────────────────`);
  console.log(`  Server:  http://localhost:${PORT}`);
  console.log(`  Local:   ${localIP}`);
  console.log(`  Subnet:  ${subnet}.0/24`);
  console.log(`  Interfaces:`);
  ifaces.forEach(i => console.log(`    - ${i.name}: ${i.address}/${i.netmask}`));
  console.log(`\n  Open the URL above in your browser.\n`);
});
