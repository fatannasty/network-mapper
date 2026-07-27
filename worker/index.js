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
      // ── Locations ──

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

      // ── Scan Push ──

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
        return Response.json({ success: true, locationId, deviceCount: devices.length }, { headers: corsHeaders });
      }

      // ── History ──

      if (url.pathname === '/api/history' && request.method === 'GET') {
        const locationId = url.searchParams.get('location');
        if (!locationId) return Response.json({ error: 'location param required' }, { status: 400, headers: corsHeaders });
        const list = await env.SCANS.list({ prefix: `history:${locationId}:`, limit: 50 });
        const history = [];
        for (const key of list.keys) {
          const data = await env.SCANS.get(key.name, 'json');
          if (data) history.push(data);
        }
        history.sort((a, b) => new Date(b.scannedAt) - new Date(a.scannedAt));
        return Response.json(history, { headers: corsHeaders });
      }

      // ── Agent ──

      if (url.pathname === '/api/agent/register' && request.method === 'POST') {
        const body = await request.json();
        const { agentId, locationId, locationName, ip } = body;
        await env.SCANS.put(`agent:${agentId}`, JSON.stringify({
          agentId, locationId, locationName: locationName || locationId, ip,
          registeredAt: new Date().toISOString(), lastSeen: new Date().toISOString(),
        }), { expirationTtl: 86400 });
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

      // ── Catalyst Center Test ──

      if (url.pathname === '/api/catc/test' && request.method === 'POST') {
        const body = await request.json();
        const { url: catcUrl, user, pass } = body;

        if (!catcUrl || !user || !pass) {
          return Response.json({ success: false, error: 'Missing URL, username, or password' }, { headers: corsHeaders });
        }

        try {
          const auth = btoa(`${user}:${pass}`);
          const tokenRes = await fetch(`${catcUrl}/dna/system/api/v1/auth/token`, {
            method: 'POST',
            headers: { 'Authorization': `Basic ${auth}`, 'Content-Type': 'application/json' },
          });

          if (!tokenRes.ok) {
            const errText = await tokenRes.text();
            return Response.json({ success: false, error: `Auth failed (${tokenRes.status}): ${errText.substring(0, 200)}` }, { headers: corsHeaders });
          }

          const tokenData = await tokenRes.json();
          if (!tokenData.Token) {
            return Response.json({ success: false, error: 'No token returned. Check credentials.' }, { headers: corsHeaders });
          }

          const deviceRes = await fetch(`${catcUrl}/dna/intent/api/v1/network-device`, {
            headers: { 'X-Auth-Token': tokenData.Token, 'Content-Type': 'application/json' },
          });
          const deviceData = await deviceRes.json();
          const count = Array.isArray(deviceData?.response) ? deviceData.response.length : 0;

          return Response.json({ success: true, deviceCount: count }, { headers: corsHeaders });
        } catch (e) {
          return Response.json({ success: false, error: `Connection failed: ${e.message}` }, { headers: corsHeaders });
        }
      }

      // ── Catalyst Center Scan ──

      if (url.pathname === '/api/catc/scan' && request.method === 'POST') {
        const body = await request.json();
        const { url: catcUrl, user, pass } = body;

        if (!catcUrl || !user || !pass) {
          return Response.json({ success: false, error: 'Missing URL, username, or password' }, { headers: corsHeaders });
        }

        try {
          const auth = btoa(`${user}:${pass}`);
          const tokenRes = await fetch(`${catcUrl}/dna/system/api/v1/auth/token`, {
            method: 'POST',
            headers: { 'Authorization': `Basic ${auth}`, 'Content-Type': 'application/json' },
          });
          const tokenData = await tokenRes.json();
          if (!tokenData.Token) return Response.json({ success: false, error: 'Auth failed' }, { headers: corsHeaders });
          const token = tokenData.Token;

          const deviceRes = await fetch(`${catcUrl}/dna/intent/api/v1/network-device`, {
            headers: { 'X-Auth-Token': token, 'Content-Type': 'application/json' },
          });
          const deviceData = await deviceRes.json();
          const devices = deviceData?.response || [];

          let sites = [];
          try {
            const siteRes = await fetch(`${catcUrl}/dna/intent/api/v1/site`, {
              headers: { 'X-Auth-Token': token, 'Content-Type': 'application/json' },
            });
            const siteData = await siteRes.json();
            sites = siteData?.response || [];
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

          const mapDevice = (d) => ({
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
          });

          const saveLocation = async (locId, locName, devs) => {
            const locationData = {
              name: locName,
              subnet: 'catalyst-center',
              deviceCount: devs.length,
              scannedAt: new Date().toISOString(),
              devices: devs.map(mapDevice),
              connections: [],
            };
            await env.SCANS.put(`location:${locId}`, JSON.stringify(locationData));
          };

          let locationCount = 0;
          if (sites.length > 0) {
            for (const site of sites) {
              const siteId = site.id || site.siteId;
              const siteName = site.name || site.siteNameHierarchy || `Site-${siteId}`;
              try {
                const memberRes = await fetch(`${catcUrl}/dna/intent/api/v1/site/${siteId}/member/device`, {
                  headers: { 'X-Auth-Token': token, 'Content-Type': 'application/json' },
                });
                const memberData = await memberRes.json();
                const memberIds = new Set((memberData?.response || []).map(d => d.id));
                if (memberIds.size > 0) {
                  const siteDevices = devices.filter(d => memberIds.has(d.id));
                  await saveLocation(siteId, siteName, siteDevices);
                  locationCount++;
                }
              } catch {}
            }
          }

          if (locationCount === 0) {
            await saveLocation('catalyst-center', 'Catalyst Center', devices);
            locationCount = 1;
          }

          return Response.json({ success: true, deviceCount: devices.length, locationCount }, { headers: corsHeaders });
        } catch (e) {
          return Response.json({ success: false, error: e.message }, { headers: corsHeaders });
        }
      }

      return Response.json({ error: 'Not found' }, { status: 404, headers: corsHeaders });

    } catch (err) {
      return Response.json({ error: err.message }, { status: 500, headers: corsHeaders });
    }
  }
};
