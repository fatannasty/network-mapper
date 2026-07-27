const express = require('express');
const http = require('http');
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
  res.json({
    localIP: scanner.getLocalIP(),
    subnet: scanner.getSubnet(),
    suggestedCIDR: `${scanner.getSubnet()}.0/24`,
    interfaces: scanner.getNetworkInterfaces(),
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
