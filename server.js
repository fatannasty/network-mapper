const express = require('express');
const http = require('http');
const https = require('https');
const { WebSocketServer } = require('ws');
const path = require('path');
const scanner = require('./scanner');
const sshScanner = require('./ssh-scanner');

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

app.post('/api/ssh/scan', async (req, res) => {
  try {
    const { host, user, pass, location } = req.body;
    if (!host || !user || !pass) {
      return res.json({ success: false, error: 'Missing host, user, or password' });
    }
    console.log(`SSH scan: ${user}@${host}`);
    const result = await sshScanner.scanCoreSwitch({ host, user, pass, location: location || '' });

    const WORKER_API = 'https://network-mapper-api.fatannasty.workers.dev';
    try {
      await catcHttpRequest(`${WORKER_API}/api/scan`, {
        method: 'POST',
        body: {
          locationId: location || host,
          locationName: result.hostname || location || host,
          devices: result.devices,
          connections: result.connections,
          subnet: host,
          scannedAt: new Date().toISOString(),
        },
      });
    } catch (e) { console.log('Worker push failed:', e.message); }

    res.json({
      success: true,
      hostname: result.hostname,
      model: result.model,
      devices: result.devices,
      connections: result.connections,
      cdpNeighbors: result.cdpNeighbors.length,
      macEntries: result.macTable.length,
      arpEntries: result.arpTable.length,
      vlans: result.vlans.length,
    });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

app.post('/api/catc/test', async (req, res) => {
  try {
    let { url, user, pass } = req.body;
    if (!url) return res.json({ success: false, error: 'URL is required' });
    if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
    let baseUrl = url.replace(/\/+$/, '');
    const parsed = new URL(baseUrl);
    parsed.pathname = '/dna/system/api/v1/auth/token';
    const authUrl = parsed.toString();
    const auth = Buffer.from(`${user}:${pass}`).toString('base64');
    console.log(`CatC auth: POST ${authUrl} user=${user}`);
    const tokenRes = await catcHttpRequest(authUrl, {
      method: 'POST',
      headers: { 'Authorization': `Basic ${auth}` },
    });
    console.log(`CatC auth response: status=${tokenRes.status}`);
    if (tokenRes.status !== 200 || !tokenRes.data?.Token) {
      const respSnippet = JSON.stringify(tokenRes.data).slice(0, 200);
      console.log(`CatC auth body: ${respSnippet}`);
      return res.json({ success: false, error: `Auth failed (${tokenRes.status})` });
    }
    parsed.pathname = '/dna/intent/api/v1/network-device';
    const deviceRes = await catcHttpRequest(parsed.toString(), {
      headers: { 'X-Auth-Token': tokenRes.data.Token },
    });
    const count = Array.isArray(deviceRes.data?.response) ? deviceRes.data.response.length : 0;
    let sites = [];
    try {
      parsed.pathname = '/dna/intent/api/v1/site';
      const siteRes = await catcHttpRequest(parsed.toString(), {
        headers: { 'X-Auth-Token': tokenRes.data.Token },
      });
      sites = siteRes.data?.response || [];
      console.log(`CatC sites: ${sites.length} found`);
      if (sites.length > 0) console.log('First site:', JSON.stringify(sites[0]).slice(0, 200));
    } catch (e) { console.log('CatC sites error:', e.message); }
    res.json({ success: true, deviceCount: count, sites });
  } catch (e) {
    res.json({ success: false, error: e.message });
  }
});

app.post('/api/catc/scan', async (req, res) => {
  try {
    let { url, user, pass, siteIds } = req.body;
    if (!url) return res.json({ success: false, error: 'URL is required' });
    if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
    let baseUrl = url.replace(/\/+$/, '');
    const parsed = new URL(baseUrl);
    const auth = Buffer.from(`${user}:${pass}`).toString('base64');
    parsed.pathname = '/dna/system/api/v1/auth/token';
    const tokenRes = await catcHttpRequest(parsed.toString(), {
      method: 'POST',
      headers: { 'Authorization': `Basic ${auth}` },
      timeout: 15000,
    });
    if (tokenRes.status !== 200 || !tokenRes.data?.Token) {
      return res.json({ success: false, error: `Auth failed (${tokenRes.status})` });
    }
    const token = tokenRes.data.Token;
    const allDevices = [];

    if (Array.isArray(siteIds) && siteIds.length > 0) {
      for (const siteId of siteIds) {
        try {
          parsed.pathname = `/dna/intent/api/v1/site/${siteId}/member/device`;
          const memberRes = await catcHttpRequest(parsed.toString(), {
            headers: { 'X-Auth-Token': token },
            timeout: 15000,
          });
          const members = memberRes.data?.response || [];
          allDevices.push(...members);
        } catch (e) {
          console.log(`Site ${siteId} failed:`, e.message);
        }
      }
    } else {
      parsed.pathname = '/dna/intent/api/v1/network-device';
      const deviceRes = await catcHttpRequest(parsed.toString(), {
        headers: { 'X-Auth-Token': token },
        timeout: 30000,
      });
      const devices = deviceRes.data?.response || [];
      allDevices.push(...devices);
    }

    const mapType = (d) => {
      const f = (d.family || '').toLowerCase();
      const p = (d.platformId || '').toLowerCase();
      if (f.includes('router') || p.includes('isr')) return 'router';
      if (f.includes('switch') || p.includes('catalyst') || p.includes('nexus')) return 'switch';
      if (f.includes('wireless') || p.includes('wlc') || p.includes('ap')) return 'accesspoint';
      if (f.includes('firewall') || p.includes('asa') || p.includes('ftd')) return 'firewall';
      return 'pc';
    };

    const mapped = allDevices.map(d => ({
      ip: d.managementIpAddress || '',
      hostname: d.hostname || d.serialNumber || '',
      type: mapType(d),
      model: d.platformId || '',
      vendor: 'Cisco',
      mac: d.macAddress || '',
      location: d.locationName || d.siteName || '',
    }));

    const excludePCs = req.body.excludePCs !== false;
    const filtered = excludePCs ? mapped.filter(d => d.type !== 'pc') : mapped;

    res.json({ success: true, devices: filtered, connections: [] });
  } catch (e) {
    console.error('CatC scan error:', e);
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
