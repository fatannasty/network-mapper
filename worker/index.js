export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    try {
      if (url.pathname === '/api/locations' && request.method === 'GET') {
        const list = await env.SCANS.list({ prefix: 'location:' });
        const locations = [];
        for (const key of list.keys) {
          const data = await env.SCANS.get(key.name, 'json');
          if (data) locations.push({ id: key.name.replace('location:', ''), ...data });
        }
        return Response.json(locations, { headers: corsHeaders });
      }

      if (url.pathname.match(/^\/api\/location\/[^/]+$/) && request.method === 'GET') {
        const id = url.pathname.split('/').pop();
        const data = await env.SCANS.get(`location:${id}`, 'json');
        if (!data) return Response.json({ error: 'Location not found' }, { status: 404, headers: corsHeaders });
        return Response.json({ id, ...data }, { headers: corsHeaders });
      }

      if (url.pathname === '/api/scan' && request.method === 'POST') {
        const body = await request.json();
        const { locationId, locationName, devices, connections, subnet, scannedAt } = body;

        if (!locationId || !devices) {
          return Response.json({ error: 'locationId and devices required' }, { status: 400, headers: corsHeaders });
        }

        const locationData = {
          name: locationName || locationId,
          subnet: subnet || 'unknown',
          deviceCount: devices.length,
          scannedAt: scannedAt || new Date().toISOString(),
          devices,
          connections: connections || [],
        };

        await env.SCANS.put(`location:${locationId}`, JSON.stringify(locationData));

        const historyKey = `history:${locationId}:${Date.now()}`;
        await env.SCANS.put(historyKey, JSON.stringify(locationData), { expirationTtl: 86400 * 30 });

        return Response.json({ success: true, locationId, deviceCount: devices.length }, { headers: corsHeaders });
      }

      if (url.pathname === '/api/history' && request.method === 'GET') {
        const locationId = url.searchParams.get('location');
        if (!locationId) {
          return Response.json({ error: 'location param required' }, { status: 400, headers: corsHeaders });
        }
        const list = await env.SCANS.list({ prefix: `history:${locationId}:`, limit: 50 });
        const history = [];
        for (const key of list.keys) {
          const data = await env.SCANS.get(key.name, 'json');
          if (data) history.push(data);
        }
        history.sort((a, b) => new Date(b.scannedAt) - new Date(a.scannedAt));
        return Response.json(history, { headers: corsHeaders });
      }

      if (url.pathname === '/api/agent/register' && request.method === 'POST') {
        const body = await request.json();
        const { agentId, locationId, locationName, ip } = body;
        const agentData = {
          agentId,
          locationId,
          locationName: locationName || locationId,
          ip,
          registeredAt: new Date().toISOString(),
          lastSeen: new Date().toISOString(),
        };
        await env.SCANS.put(`agent:${agentId}`, JSON.stringify(agentData), { expirationTtl: 86400 });
        return Response.json({ success: true }, { headers: corsHeaders });
      }

      if (url.pathname === '/api/agent/heartbeat' && request.method === 'POST') {
        const body = await request.json();
        const { agentId } = body;
        const agent = await env.SCANS.get(`agent:${agentId}`, 'json');
        if (agent) {
          agent.lastSeen = new Date().toISOString();
          await env.SCANS.put(`agent:${agentId}`, JSON.stringify(agent), { expirationTtl: 86400 });
        }
        return Response.json({ success: true }, { headers: corsHeaders });
      }

      return Response.json({ error: 'Not found' }, { status: 404, headers: corsHeaders });

    } catch (err) {
      return Response.json({ error: err.message }, { status: 500, headers: corsHeaders });
    }
  }
};
