(() => {
  const canvas = document.getElementById('topology-canvas');
  const ctx = canvas.getContext('2d');
  const tooltip = document.getElementById('tooltip');
  const propertiesPanel = document.getElementById('properties-panel');
  const fileInput = document.getElementById('file-input');

  let devices = [];
  let connections = [];
  let mode = 'select';
  let selectedDevice = null;
  let draggingDevice = null;
  let dragOffset = { x: 0, y: 0 };
  let connectStart = null;
  let mousePos = { x: 0, y: 0 };
  let hoveredDevice = null;
  let selectedConnection = null;
  let hoveredConnection = null;
  let nextId = 1;

  const GRID_SIZE = 20;
  const DEVICE_RADIUS = 30;

  const DEVICE_COLORS = {
    router:           { fill: '#3b82f6', stroke: '#1e40af', icon: 'R', svg: 'icons/router.svg' },
    'core-switch':    { fill: '#a855f7', stroke: '#7c3aed', icon: 'CS', svg: 'icons/C9300X-24Y.png' },
    'access-switch':  { fill: '#20c997', stroke: '#12b886', icon: 'AS', svg: 'icons/C9200-24P.png' },
    switch:           { fill: '#f97316', stroke: '#ea580c', icon: 'S', svg: 'icons/C9300L-48P.png' },
    accesspoint:      { fill: '#3b82f6', stroke: '#2563eb', icon: 'AP', svg: 'icons/meraki-mr46.png' },
    'velocloud-edge': { fill: '#8b5cf6', stroke: '#7c3aed', icon: 'VE', svg: 'icons/velocloud-edge-510.png' },
    firewall:         { fill: '#ef4444', stroke: '#dc2626', icon: 'FW', svg: 'icons/firewall-cisco.svg' },
    server:           { fill: '#8b5cf6', stroke: '#7c3aed', icon: 'SV', svg: 'icons/server-cisco.svg' },
    pc:               { fill: '#6366f1', stroke: '#4f46e5', icon: 'PC', svg: 'icons/pc-cisco.svg' },
    cloud:            { fill: '#06b6d4', stroke: '#0891b2', icon: '☁', svg: 'icons/cloud-cisco.svg' },
  };

  const SWITCH_MODELS = {
    'C9200-24P':     { svg: 'icons/C9200-24P.png', type: 'access-switch' },
    'C9200-48P':     { svg: 'icons/C9200-48P.png', type: 'access-switch' },
    'C9200-24T':     { svg: 'icons/C9200-24P.png', type: 'access-switch' },
    'C9200-48T':     { svg: 'icons/C9200-48P.png', type: 'access-switch' },
    'C9200CX-12-2X2G': { svg: 'icons/C9200CX-12-2X2G.jpg', type: 'access-switch' },
    'C9200CX-8P-2X2G': { svg: 'icons/C9200CX-8P-2X2G.jpg', type: 'access-switch' },
    'C9300-24T':     { svg: 'icons/C9300L-24P.png', type: 'switch' },
    'C9300-48T':     { svg: 'icons/C9300L-48P.png', type: 'switch' },
    'C9300-24U':     { svg: 'icons/C9300L-24P.png', type: 'switch' },
    'C9300-48U':     { svg: 'icons/C9300L-48P.png', type: 'switch' },
    'C9300L-24P':    { svg: 'icons/C9300L-24P.png', type: 'switch' },
    'C9300L-48P':    { svg: 'icons/C9300L-48P.png', type: 'switch' },
    'C9300X-12Y':    { svg: 'icons/C9300X-12Y.png', type: 'switch' },
    'C9300X-24Y':    { svg: 'icons/C9300X-24Y.png', type: 'switch' },
    'C9300X-24T':    { svg: 'icons/C9300X-24Y.png', type: 'switch' },
    'C9400-7S':      { svg: 'icons/C9300X-24Y.png', type: 'core-switch' },
    'C9400-10S':     { svg: 'icons/C9300X-24Y.png', type: 'core-switch' },
    'C9500-12Q':     { svg: 'icons/C9300X-24Y.png', type: 'core-switch' },
    'C9500-24Y4C':   { svg: 'icons/C9300X-24Y.png', type: 'core-switch' },
    'C9500-48Y4C':   { svg: 'icons/C9300X-24Y.png', type: 'core-switch' },
    'IE-3300-8P2S':  { svg: 'icons/IE-3300-8P2S.png', type: 'switch' },
    'IE-3400-8P2S-E':{ svg: 'icons/IE-3400-8P2S-E.png', type: 'switch' },
    'IEM-3300-14T2S':{ svg: 'icons/IEM-3300-14T2S.png', type: 'switch' },
    'IEM-3300-16P':  { svg: 'icons/IEM-3300-16P.png', type: 'switch' },
    'IEM-3300-8S':   { svg: 'icons/IEM-3300-8S.png', type: 'switch' },
  };

  const AP_MODELS = {
    'MR28':  { svg: 'icons/meraki-mr28.png', type: 'accesspoint' },
    'MR36':  { svg: 'icons/meraki-mr36.png', type: 'accesspoint' },
    'MR38':  { svg: 'icons/meraki-mr36.png', type: 'accesspoint' },
    'MR44':  { svg: 'icons/meraki-mr44.png', type: 'accesspoint' },
    'MR45':  { svg: 'icons/meraki-mr45.png', type: 'accesspoint' },
    'MR46':  { svg: 'icons/meraki-mr46.png', type: 'accesspoint' },
    'MR48':  { svg: 'icons/meraki-mr46.png', type: 'accesspoint' },
    'MR56':  { svg: 'icons/meraki-mr56.png', type: 'accesspoint' },
    'MR58':  { svg: 'icons/meraki-mr56.png', type: 'accesspoint' },
  };

  const VELOCLOUD_MODELS = {
    'VCE-510':  { svg: 'icons/velocloud-edge-510.png', type: 'velocloud-edge' },
    'VCE-610':  { svg: 'icons/velocloud-edge-510.png', type: 'velocloud-edge' },
    'VCE-640':  { svg: 'icons/velocloud-edge-510.png', type: 'velocloud-edge' },
    'VCE-680':  { svg: 'icons/velocloud-edge-510.png', type: 'velocloud-edge' },
    'VCE-710':  { svg: 'icons/velocloud-edge-510.png', type: 'velocloud-edge' },
    'VCE-840':  { svg: 'icons/velocloud-edge-rackmount.svg', type: 'velocloud-edge' },
    'VCE-2000': { svg: 'icons/velocloud-edge-rackmount.svg', type: 'velocloud-edge' },
    'VCE-3400': { svg: 'icons/velocloud-edge-rackmount.svg', type: 'velocloud-edge' },
    'VCE-3800': { svg: 'icons/velocloud-edge-rackmount.svg', type: 'velocloud-edge' },
  };

  function getModelsForType(type) {
    if (type === 'accesspoint') return Object.keys(AP_MODELS);
    if (type === 'velocloud-edge') return Object.keys(VELOCLOUD_MODELS);
    if (['switch', 'access-switch', 'core-switch'].includes(type)) return Object.keys(SWITCH_MODELS);
    return [];
  }

  const modelIcons = {};
  let modelIconsLoaded = false;

  function loadModelIcons() {
    const allModels = { ...SWITCH_MODELS, ...AP_MODELS, ...VELOCLOUD_MODELS };
    const uniqueSvgs = [...new Set(Object.values(allModels).map(m => m.svg))];
    const promises = uniqueSvgs.map(svg => {
      return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => { modelIcons[svg] = img; resolve(); };
        img.onerror = () => { console.warn('Failed to load:', svg); resolve(); };
        img.src = svg;
      });
    });
    Promise.all(promises).then(() => { modelIconsLoaded = true; draw(); });
  }

  const CABLE_TYPES = {
    'mm-fiber':{ color: '#f59d56', label: 'Multi-mode Fiber', dash: [8, 4], legendId: 'legend-mm-color' },
    copper:    { color: '#10b981', label: 'Copper', dash: [], legendId: 'legend-copper-color' },
    'sm-fiber':{ color: '#eab308', label: 'Single-mode Fiber', dash: [4, 4], legendId: 'legend-sm-color' },
    dac:       { color: '#ef4444', label: 'DAC', dash: [2, 3] },
    unknown:   { color: '#64748b', label: 'Unknown', dash: [] },
  };

  function getCableColor(type) {
    const cable = CABLE_TYPES[type] || CABLE_TYPES.unknown;
    if (cable.legendId) {
      const input = document.getElementById(cable.legendId);
      if (input && input.value) return input.value;
    }
    return cable.color;
  }

  const iconImages = {};
  let iconsLoaded = false;

  function loadIcons() {
    const promises = Object.entries(DEVICE_COLORS).map(([type, colors]) => {
      return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => { iconImages[type] = img; resolve(); };
        img.onerror = () => resolve();
        img.src = colors.svg;
      });
    });
    Promise.all(promises).then(() => { iconsLoaded = true; draw(); });
  }

  const DEVICE_NAMES = {
    router: 'Router',
    'core-switch': 'Core Switch',
    'access-switch': 'Access Switch',
    switch: 'Switch',
    accesspoint: 'Access Point',
    'velocloud-edge': 'VeloCloud Edge',
    firewall: 'Firewall',
    server: 'Server',
    pc: 'Workstation',
    cloud: 'Cloud',
  };

  function resizeCanvas() {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * devicePixelRatio;
    canvas.height = rect.height * devicePixelRatio;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    draw();
  }

  function snapToGrid(v) {
    return Math.round(v / GRID_SIZE) * GRID_SIZE;
  }

  function drawGrid() {
    const w = canvas.width / devicePixelRatio;
    const h = canvas.height / devicePixelRatio;
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.08)';
    ctx.lineWidth = 0.5;
    for (let x = 0; x <= w; x += GRID_SIZE) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let y = 0; y <= h; y += GRID_SIZE) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
  }

  function drawConnections() {
    connections.forEach(conn => {
      const a = devices.find(d => d.id === conn.from);
      const b = devices.find(d => d.id === conn.to);
      if (!a || !b) return;

      const isSelected = selectedConnection === conn;
      const isHovered = hoveredConnection === conn;
      const cable = CABLE_TYPES[conn.cableType] || CABLE_TYPES.unknown;

      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);

      if (isSelected) {
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 4;
        ctx.shadowColor = '#38bdf8';
        ctx.shadowBlur = 8;
      } else if (isHovered) {
        ctx.strokeStyle = '#60a5fa';
        ctx.lineWidth = 3;
        ctx.shadowColor = '#60a5fa';
        ctx.shadowBlur = 6;
      } else {
        ctx.strokeStyle = getCableColor(conn.cableType);
        ctx.lineWidth = 2;
        ctx.shadowBlur = 0;
      }

      ctx.setLineDash(cable.dash);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.shadowBlur = 0;

      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2;
      const angle = Math.atan2(b.y - a.y, b.x - a.x);
      const perpX = -Math.sin(angle) * 14;
      const perpY = Math.cos(angle) * 14;
      const lx = conn.labelOffset ? (conn.labelOffset.x || mx + perpX * 0.5) : mx + perpX * 0.5;
      const ly = conn.labelOffset ? (conn.labelOffset.y || my + perpY * 0.5) : my + perpY * 0.5;

      const showCable = conn.cableType && conn.cableType !== 'unknown';

      const labelPieces = [];
      if (conn.label) labelPieces.push(conn.label);
      if (showCable) labelPieces.push(cable.label);
      const labelText = labelPieces.join(' · ');
      if (!labelText && !conn.vlanUp && !conn.vlanDown) return;

      const PAD = 5;
      const FONT = '500 11px "Segoe UI", system-ui, sans-serif';
      const FONT_TAG = '600 9px "Segoe UI", system-ui, sans-serif';

      ctx.font = FONT;
      const labelW = labelText ? Math.ceil(ctx.measureText(labelText).width) : 0;

      const vlanTags = [];
      if (conn.vlanUp) vlanTags.push({ text: `${conn.vlanUp}`, color: '#f59e0b' });
      if (conn.vlanDown) vlanTags.push({ text: `${conn.vlanDown}`, color: '#10b981' });

      let vlanW = 0;
      if (vlanTags.length > 0) {
        ctx.font = FONT_TAG;
        for (const t of vlanTags) {
          vlanW += Math.ceil(ctx.measureText(t.text).width) + 16;
        }
      }

      const contentW = Math.max(labelW, vlanW);
      const totalW = contentW + PAD * 2 + 8;
      const totalH = 22;
      const bx = lx - totalW / 2;
      const by = ly - totalH / 2;

      ctx.save();
      roundRect(ctx, bx, by, totalW, totalH, 4);
      ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
      ctx.fill();

      if (showCable && labelText) {
        ctx.fillStyle = getCableColor(conn.cableType);
        roundRect(ctx, bx + 2, by + 3, 3, totalH - 6, 1.5);
        ctx.fill();
      }

      let cursorX = bx + PAD + 6;
      if (labelText) {
        ctx.font = FONT;
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(labelText, cursorX, by + totalH / 2);
        cursorX += labelW + 6;
      }

      for (const tag of vlanTags) {
        ctx.font = FONT_TAG;
        const tw = Math.ceil(ctx.measureText(tag.text).width);
        const tagW = tw + 8;
        roundRect(ctx, cursorX, by + 4, tagW, 14, 3);
        ctx.fillStyle = tag.color;
        ctx.fill();
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(tag.text, cursorX + tagW / 2, by + 11);
        cursorX += tagW + 4;
      }

      ctx.restore();
    });
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  function drawDevice(d) {
    const colors = DEVICE_COLORS[d.type] || DEVICE_COLORS.pc;
    const r = DEVICE_RADIUS;
    const isSelected = selectedDevice && selectedDevice.id === d.id;
    const isHovered = hoveredDevice && hoveredDevice.id === d.id;

    ctx.save();

    if (isSelected || isHovered) {
      ctx.beginPath();
      ctx.arc(d.x, d.y, r + 6, 0, Math.PI * 2);
      ctx.strokeStyle = isSelected ? '#38bdf8' : '#64748b';
      ctx.lineWidth = 2;
      ctx.setLineDash(isSelected ? [] : [4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    drawDeviceIcon(d.type, d.x, d.y, r, colors, d.model);

    ctx.fillStyle = '#000000';
    ctx.font = 'bold 14px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(d.name, d.x, d.y + r + 6);

    let yOffset = r + 24;
    if (d.ip) {
      ctx.fillStyle = '#000000';
      ctx.font = '12px sans-serif';
      ctx.fillText(d.ip, d.x, d.y + yOffset);
      yOffset += 16;
    }

    if (d.location) {
      ctx.fillStyle = '#000000';
      ctx.font = '11px sans-serif';
      ctx.fillText(d.location, d.x, d.y + yOffset);
      yOffset += 14;
    }

    if (d.model) {
      ctx.fillStyle = '#000000';
      ctx.font = '11px monospace';
      ctx.fillText(d.model, d.x, d.y + yOffset);
      yOffset += 14;
    }

    const connPorts = connections.filter(c => c.from === d.id || c.to === d.id);
    for (const c of connPorts) {
      const peer = devices.find(p => p.id === (c.from === d.id ? c.to : c.from));
      if (!peer) continue;
      const thisPort = c.from === d.id ? c.portA : c.portB;
      if (!thisPort) continue;
      ctx.fillStyle = '#64748b';
      ctx.font = '10px "Segoe UI", sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(`${thisPort} → ${peer.name}`, d.x, d.y + yOffset);
      yOffset += 13;
    }

    ctx.restore();
  }

  function drawDeviceIcon(type, x, y, r, colors, model) {
    ctx.save();

    if (model && modelIconsLoaded) {
      const models = type === 'accesspoint' ? AP_MODELS : (VELOCLOUD_MODELS[model] ? VELOCLOUD_MODELS : SWITCH_MODELS);
      const modelInfo = models[model];
      if (modelInfo && modelIcons[modelInfo.svg]) {
        const img = modelIcons[modelInfo.svg];
        const isPng = modelInfo.svg.endsWith('.png') || modelInfo.svg.endsWith('.jpg');

        if (isPng) {
          const maxW = r * 4;
          const maxH = r * 2.5;
          const scale = Math.min(maxW / img.naturalWidth, maxH / img.naturalHeight, 1);
          const w = img.naturalWidth * scale;
          const h = img.naturalHeight * scale;

          ctx.imageSmoothingEnabled = true;
          ctx.imageSmoothingQuality = 'high';
          ctx.drawImage(img, x - w / 2, y - h / 2, w, h);
        } else {
          const size = r * 2.2;
          ctx.imageSmoothingEnabled = true;
          ctx.imageSmoothingQuality = 'high';
          ctx.drawImage(img, x - size / 2, y - size / 2, size, size);
        }
        ctx.restore();
        return;
      }
    }

    if (iconsLoaded && iconImages[type]) {
      const img = iconImages[type];
      const isPng = DEVICE_COLORS[type]?.svg?.endsWith('.png') || DEVICE_COLORS[type]?.svg?.endsWith('.jpg');

      if (isPng) {
        const maxW = r * 4;
        const maxH = r * 2.5;
        const scale = Math.min(maxW / img.naturalWidth, maxH / img.naturalHeight, 1);
        const w = img.naturalWidth * scale;
        const h = img.naturalHeight * scale;

        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(img, x - w / 2, y - h / 2, w, h);
      } else {
        const size = r * 2.2;
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(img, x - size / 2, y - size / 2, size, size);
      }
      ctx.restore();
      return;
    }

    const s = r / 24;

    switch (type) {
      case 'router':
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fillStyle = colors.fill;
        ctx.fill();
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(x, y, r * 0.55, 0, Math.PI * 2);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x - r * 0.35, y);
        ctx.lineTo(x + r * 0.35, y);
        ctx.moveTo(x, y - r * 0.35);
        ctx.lineTo(x, y + r * 0.35);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        const arrowLen = r * 0.22;
        [[-1, 0], [1, 0], [0, -1], [0, 1]].forEach(([dx, dy]) => {
          const ax = x + dx * r * 0.55;
          const ay = y + dy * r * 0.55;
          ctx.beginPath();
          ctx.moveTo(ax, ay);
          ctx.lineTo(ax + dx * arrowLen, ay + dy * arrowLen);
          ctx.strokeStyle = '#fff';
          ctx.lineWidth = 2;
          ctx.stroke();
        });
        break;

      case 'switch':
        ctx.beginPath();
        const swW = r * 1.6;
        const swH = r * 0.9;
        ctx.roundRect(x - swW / 2, y - swH / 2, swW, swH, 4);
        ctx.fillStyle = colors.fill;
        ctx.fill();
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
        const portCount = 6;
        const portSpacing = (swW - 8) / portCount;
        const portW = portSpacing * 0.5;
        const portH = swH * 0.35;
        for (let i = 0; i < portCount; i++) {
          const px = x - swW / 2 + 4 + portSpacing * i + (portSpacing - portW) / 2;
          const py = y - portH / 2;
          ctx.fillStyle = '#fff';
          ctx.fillRect(px, py, portW, portH);
        }
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(x - swW / 2 + 6, y + swH / 2 - 4, 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#4ade80';
        ctx.beginPath();
        ctx.arc(x - swW / 2 + 12, y + swH / 2 - 4, 2, 0, Math.PI * 2);
        ctx.fill();
        break;

      case 'accesspoint':
        ctx.beginPath();
        ctx.arc(x, y + r * 0.2, r * 0.5, 0, Math.PI * 2);
        ctx.fillStyle = colors.fill;
        ctx.fill();
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(x, y + r * 0.2, r * 0.15, 0, Math.PI * 2);
        ctx.fill();
        [0.35, 0.55, 0.75].forEach(scale => {
          ctx.beginPath();
          ctx.arc(x, y + r * 0.2, r * scale, -Math.PI * 0.8, -Math.PI * 0.2);
          ctx.strokeStyle = colors.fill;
          ctx.lineWidth = 2;
          ctx.stroke();
        });
        ctx.beginPath();
        ctx.moveTo(x, y + r * 0.2);
        ctx.lineTo(x, y - r * 0.5);
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
        break;

      case 'firewall':
        ctx.beginPath();
        const fwW = r * 1.4;
        const fwH = r * 1.6;
        ctx.roundRect(x - fwW / 2, y - fwH / 2, fwW, fwH, 3);
        ctx.fillStyle = colors.fill;
        ctx.fill();
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.fillStyle = '#fff';
        const brickH = fwH / 4;
        for (let row = 0; row < 4; row++) {
          const by = y - fwH / 2 + row * brickH + 2;
          const offset = row % 2 === 0 ? 0 : fwW * 0.25;
          for (let col = 0; col < 2; col++) {
            const bx = x - fwW / 2 + 2 + col * fwW * 0.5 + offset;
            const bw = fwW * 0.5 - 4;
            ctx.fillRect(bx, by + 1, bw, brickH - 3);
          }
        }
        ctx.fillStyle = colors.fill;
        ctx.beginPath();
        ctx.arc(x, y, r * 0.25, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, y - r * 0.15);
        ctx.lineTo(x, y + r * 0.15);
        ctx.moveTo(x - r * 0.12, y + r * 0.05);
        ctx.lineTo(x + r * 0.12, y + r * 0.05);
        ctx.stroke();
        break;

      case 'server':
        const rackH = r * 1.6;
        const rackW = r * 1.2;
        const unitH = rackH / 3;
        for (let i = 0; i < 3; i++) {
          const uy = y - rackH / 2 + i * unitH + 1;
          ctx.beginPath();
          ctx.roundRect(x - rackW / 2, uy, rackW, unitH - 2, 2);
          ctx.fillStyle = i === 0 ? colors.fill : (i === 1 ? colors.fill : colors.fill);
          ctx.fill();
          ctx.strokeStyle = colors.stroke;
          ctx.lineWidth = 1.5;
          ctx.stroke();
          ctx.fillStyle = '#fff';
          ctx.beginPath();
          ctx.arc(x - rackW / 2 + 6, uy + (unitH - 2) / 2, 2, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = '#4ade80';
          ctx.beginPath();
          ctx.arc(x - rackW / 2 + 12, uy + (unitH - 2) / 2, 2, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = '#fff';
          ctx.fillRect(x - rackW / 2 + 18, uy + 3, rackW * 0.4, 2);
          ctx.fillRect(x - rackW / 2 + 18, uy + (unitH - 2) / 2 + 2, rackW * 0.3, 2);
        }
        break;

      case 'pc':
        const monW = r * 1.6;
        const monH = r * 1.1;
        ctx.beginPath();
        ctx.roundRect(x - monW / 2, y - monH / 2 - r * 0.15, monW, monH, 3);
        ctx.fillStyle = '#1e293b';
        ctx.fill();
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.beginPath();
        ctx.roundRect(x - monW / 2 + 3, y - monH / 2 - r * 0.15 + 3, monW - 6, monH - 6, 2);
        ctx.fillStyle = colors.fill;
        ctx.globalAlpha = 0.3;
        ctx.fill();
        ctx.globalAlpha = 1;
        ctx.strokeStyle = colors.fill;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(x - r * 0.25, y + monH / 2 - r * 0.15);
        ctx.lineTo(x + r * 0.25, y + monH / 2 - r * 0.15);
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.beginPath();
        ctx.roundRect(x - r * 0.4, y + monH / 2 - r * 0.05, r * 0.8, r * 0.15, 2);
        ctx.fillStyle = colors.fill;
        ctx.fill();
        break;

      case 'cloud':
        ctx.beginPath();
        ctx.arc(x - r * 0.3, y + r * 0.1, r * 0.5, Math.PI, 0);
        ctx.arc(x + r * 0.15, y - r * 0.1, r * 0.6, Math.PI * 1.2, Math.PI * 0.1);
        ctx.arc(x + r * 0.45, y + r * 0.1, r * 0.4, Math.PI * 1.5, Math.PI * 0.4);
        ctx.arc(x - r * 0.1, y + r * 0.35, r * 0.55, Math.PI * 1.8, Math.PI * 0.8);
        ctx.closePath();
        ctx.fillStyle = colors.fill;
        ctx.fill();
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
        break;

      default:
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fillStyle = colors.fill;
        ctx.fill();
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 2;
        ctx.stroke();
    }

    ctx.restore();
  }

  function drawGridPaper(w, h) {
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = '#e0e0e0';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    for (let x = 0; x <= w; x += 20) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
    }
    for (let y = 0; y <= h; y += 20) {
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
    }
    ctx.stroke();
    ctx.strokeStyle = '#cccccc';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    for (let x = 0; x <= w; x += 100) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
    }
    for (let y = 0; y <= h; y += 100) {
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
    }
    ctx.stroke();
  }

  function draw() {
    const w = canvas.width / devicePixelRatio;
    const h = canvas.height / devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    if (templateActive && templateImage && templateImage.complete) {
      drawGridPaper(w, h);
      ctx.drawImage(templateImage, 0, 0, w, h);
    } else {
      drawGrid();
    }
    drawConnections();

    if (connectStart && mode === 'connect') {
      const a = devices.find(d => d.id === connectStart);
      if (a) {
        ctx.beginPath();
        ctx.arc(a.x, a.y, DEVICE_RADIUS + 8, 0, Math.PI * 2);
        ctx.strokeStyle = '#22d3ee';
        ctx.lineWidth = 3;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.setLineDash([]);

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(mousePos.x, mousePos.y);
        ctx.strokeStyle = '#22d3ee';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    devices.forEach(d => drawDevice(d));
  }

  function deviceAt(x, y) {
    for (let i = devices.length - 1; i >= 0; i--) {
      const d = devices[i];
      const dx = d.x - x;
      const dy = d.y - y;
      const hitRadius = iconsLoaded ? DEVICE_RADIUS * 1.3 : DEVICE_RADIUS;
      if (dx * dx + dy * dy <= hitRadius * hitRadius) return d;
    }
    return null;
  }

  function findDeviceById(id) {
    return devices.find(d => d.id === id);
  }

  function updateProperties() {
    if (selectedConnection) {
      const conn = selectedConnection;
      const fromDev = devices.find(d => d.id === conn.from);
      const toDev = devices.find(d => d.id === conn.to);
      propertiesPanel.innerHTML = `
        <p style="color:#38bdf8;font-weight:600;margin-bottom:6px">Connection</p>
        <p style="font-size:13px;color:#4b5563;font-weight:500;margin-bottom:8px">${fromDev ? fromDev.name : '?'} ↔ ${toDev ? toDev.name : '?'}</p>
        <label>Link Label
          <input type="text" id="prop-conn-label" value="${conn.label || ''}" placeholder="e.g. Trunk, 1Gbps">
        </label>
        <label>Cable Type
          <select id="prop-conn-cable">
            <option value="unknown" ${!conn.cableType || conn.cableType === 'unknown' ? 'selected' : ''}>Unknown</option>
            <option value="mm-fiber" ${conn.cableType === 'mm-fiber' ? 'selected' : ''}>Multi-mode Fiber</option>
            <option value="copper" ${conn.cableType === 'copper' ? 'selected' : ''}>Copper</option>
            <option value="sm-fiber" ${conn.cableType === 'sm-fiber' ? 'selected' : ''}>Single-mode Fiber</option>
            <option value="dac" ${conn.cableType === 'dac' ? 'selected' : ''}>DAC</option>
          </select>
        </label>
        <label>Port A (${fromDev ? fromDev.name : '?'})
          <input type="text" id="prop-conn-porta" value="${conn.portA || ''}" placeholder="e.g. GI1/0/1">
        </label>
        <label>Port B (${toDev ? toDev.name : '?'})
          <input type="text" id="prop-conn-portb" value="${conn.portB || ''}" placeholder="e.g. TE1/1/1">
        </label>
        <label>Uplink VLAN
          <input type="text" id="prop-conn-vlanup" value="${conn.vlanUp || ''}" placeholder="e.g. 10, 20, 100">
        </label>
        <label>Downlink VLAN
          <input type="text" id="prop-conn-vlandown" value="${conn.vlanDown || ''}" placeholder="e.g. 30, 40, 200">
        </label>
        <button class="delete-btn" id="prop-conn-reset-label" style="margin-bottom:6px">Reset Label Position</button>
        <button class="delete-btn" id="prop-conn-delete">Delete Connection</button>
      `;
      document.getElementById('prop-conn-label').addEventListener('input', e => {
        conn.label = e.target.value;
        draw();
      });
      document.getElementById('prop-conn-cable').addEventListener('change', e => {
        conn.cableType = e.target.value;
        draw();
      });
      document.getElementById('prop-conn-porta').addEventListener('input', e => {
        conn.portA = e.target.value;
        draw();
      });
      document.getElementById('prop-conn-portb').addEventListener('input', e => {
        conn.portB = e.target.value;
        draw();
      });
      document.getElementById('prop-conn-vlanup').addEventListener('input', e => {
        conn.vlanUp = e.target.value;
        draw();
      });
      document.getElementById('prop-conn-vlandown').addEventListener('input', e => {
        conn.vlanDown = e.target.value;
        draw();
      });
      document.getElementById('prop-conn-reset-label').addEventListener('click', () => {
        delete conn.labelOffset;
        draw();
      });
      document.getElementById('prop-conn-delete').addEventListener('click', () => {
        connections = connections.filter(c => c !== conn);
        selectedConnection = null;
        updateProperties();
        draw();
      });
      return;
    }
    if (!selectedDevice) {
      propertiesPanel.innerHTML = '<p class="hint">Select a device or link to edit</p>';
      return;
    }
    const d = selectedDevice;
    const models = getModelsForType(d.type);
    propertiesPanel.innerHTML = `
      <details class="prop-section" open>
        <summary><svg class="section-arrow" width="10" height="10" viewBox="0 0 12 12"><path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>General</summary>
        <div class="prop-body">
          <label>Name
            <input type="text" id="prop-name" value="${d.name}">
          </label>
          <label>IP Address
            <input type="text" id="prop-ip" value="${d.ip || ''}" placeholder="e.g. 192.168.1.1">
          </label>
          <label>Type
            <select id="prop-type">
              ${Object.keys(DEVICE_COLORS).map(t =>
                `<option value="${t}" ${t === d.type ? 'selected' : ''}>${DEVICE_NAMES[t]}</option>`
              ).join('')}
            </select>
          </label>
          <label>Location / Site
            <input type="text" id="prop-location" value="${d.location || ''}" placeholder="e.g. Miami Station">
          </label>
        </div>
      </details>
      <details class="prop-section" ${models.length ? 'open' : ''}>
        <summary><svg class="section-arrow" width="10" height="10" viewBox="0 0 12 12"><path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>Icon &amp; Model</summary>
        <div class="prop-body">
          ${models.length ? `<label>Device Model
            <select id="prop-model">
              <option value="">— Select a model —</option>
              ${models.map(m =>
                `<option value="${m}" ${m === d.model ? 'selected' : ''}>${m}</option>`
              ).join('')}
            </select>
          </label>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px" id="icon-picker">
            ${models.map(m => {
              const allM = {...SWITCH_MODELS, ...AP_MODELS, ...VELOCLOUD_MODELS};
              const info = allM[m];
              const isActive = m === d.model;
              return info ? `<div data-model="${m}" style="width:48px;height:48px;border:2px solid ${isActive ? '#38bdf8' : '#334155'};border-radius:4px;cursor:pointer;display:flex;align-items:center;justify-content:center;background:#1e293b;overflow:hidden" title="${m}"><img src="${info.svg}" style="max-width:42px;max-height:42px;object-fit:contain" draggable="false"></div>` : '';
            }).join('')}
          </div>` : '<p style="font-size:11px;color:#64748b">No model icons available for this device type</p>'}
        </div>
      </details>
      <details class="prop-section">
        <summary><svg class="section-arrow" width="10" height="10" viewBox="0 0 12 12"><path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>Details</summary>
        <div class="prop-body">
          <label>Notes
            <input type="text" id="prop-notes" value="${d.notes || ''}" placeholder="Optional notes">
          </label>
          <label>Open Ports (comma-separated)
            <input type="text" id="prop-ports" value="${(d.ports || []).join(', ')}" placeholder="e.g. 22, 80, 443">
          </label>
        </div>
      </details>
      <button class="delete-btn" id="prop-delete">Delete Device</button>
    `;

    document.getElementById('prop-name').addEventListener('input', e => {
      d.name = e.target.value;
      draw();
    });
    document.getElementById('prop-ip').addEventListener('input', e => {
      d.ip = e.target.value;
      draw();
    });
    document.getElementById('prop-type').addEventListener('change', e => {
      d.type = e.target.value;
      d.model = '';
      document.getElementById('prop-model').value = '';
      document.getElementById('prop-model').innerHTML =
        `<option value="">— Select a model —</option>` +
        getModelsForType(d.type).map(m =>
          `<option value="${m}">${m}</option>`
        ).join('');
      draw();
    });
    document.getElementById('prop-location').addEventListener('input', e => {
      d.location = e.target.value;
      draw();
    });
    document.getElementById('prop-model').addEventListener('change', e => {
      d.model = e.target.value;
      if (d.model && SWITCH_MODELS[d.model]) {
        d.type = SWITCH_MODELS[d.model].type;
        document.getElementById('prop-type').value = d.type;
      } else if (d.model && AP_MODELS[d.model]) {
        d.type = AP_MODELS[d.model].type;
        document.getElementById('prop-type').value = d.type;
      } else if (d.model && VELOCLOUD_MODELS[d.model]) {
        d.type = VELOCLOUD_MODELS[d.model].type;
        document.getElementById('prop-type').value = d.type;
      }
      draw();
    });
    document.getElementById('prop-notes').addEventListener('input', e => {
      d.notes = e.target.value;
    });
    document.getElementById('prop-ports').addEventListener('input', e => {
      d.ports = e.target.value.split(',').map(p => parseInt(p.trim())).filter(p => !isNaN(p));
      draw();
    });
    document.getElementById('prop-delete').addEventListener('click', () => {
      deleteDevice(d.id);
    });
    const picker = document.getElementById('icon-picker');
    if (picker) {
      picker.addEventListener('click', e => {
        const div = e.target.closest('[data-model]');
        if (div) {
          const model = div.dataset.model;
          d.model = model;
          document.getElementById('prop-model').value = model;
          const allM = {...SWITCH_MODELS, ...AP_MODELS, ...VELOCLOUD_MODELS};
          const info = allM[model];
          if (info) {
            d.type = info.type;
            document.getElementById('prop-type').value = info.type;
          }
          picker.querySelectorAll('[data-model]').forEach(el => el.style.borderColor = el === div ? '#38bdf8' : '#334155');
          draw();
        }
      });
    }
  }

  function deleteDevice(id) {
    devices = devices.filter(d => d.id !== id);
    connections = connections.filter(c => c.from !== id && c.to !== id);
    if (selectedDevice && selectedDevice.id === id) selectedDevice = null;
    updateProperties();
    draw();
  }

  function setMode(newMode) {
    mode = newMode;
    document.getElementById('btn-mode-select').classList.toggle('active', mode === 'select');
    document.getElementById('btn-mode-connect').classList.toggle('active', mode === 'connect');
    canvas.classList.toggle('mode-connect', mode === 'connect');
    connectStart = null;
    draw();
  }

  document.getElementById('btn-mode-select').addEventListener('click', () => setMode('select'));
  document.getElementById('btn-mode-connect').addEventListener('click', () => setMode('connect'));

  function getCanvasPos(e) {
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  function connectionAt(x, y) {
    const threshold = 15;
    for (let i = connections.length - 1; i >= 0; i--) {
      const conn = connections[i];
      const a = devices.find(d => d.id === conn.from);
      const b = devices.find(d => d.id === conn.to);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const len2 = dx * dx + dy * dy;
      if (len2 === 0) continue;
      let t = ((x - a.x) * dx + (y - a.y) * dy) / len2;
      t = Math.max(0, Math.min(1, t));
      const px = a.x + t * dx;
      const py = a.y + t * dy;
      const dist = Math.sqrt((x - px) * (x - px) + (y - py) * (y - py));
      if (dist <= threshold) return conn;
    }
    return null;
  }

  let draggingLabel = null;

  function labelAt(x, y) {
    for (let i = connections.length - 1; i >= 0; i--) {
      const conn = connections[i];
      const a = devices.find(d => d.id === conn.from);
      const b = devices.find(d => d.id === conn.to);
      if (!a || !b) continue;
      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2;
      const angle = Math.atan2(b.y - a.y, b.x - a.x);
      const perpX = -Math.sin(angle) * 14;
      const perpY = Math.cos(angle) * 14;
      const lx = conn.labelOffset ? (conn.labelOffset.x || mx + perpX * 0.5) : mx + perpX * 0.5;
      const ly = conn.labelOffset ? (conn.labelOffset.y || my + perpY * 0.5) : my + perpY * 0.5;

      const showCable = conn.cableType && conn.cableType !== 'unknown';
      const labelPieces = [];
      if (conn.label) labelPieces.push(conn.label);
      if (showCable) labelPieces.push((CABLE_TYPES[conn.cableType] || CABLE_TYPES.unknown).label);
      const labelText = labelPieces.join(' · ');
      if (!labelText && !conn.vlanUp && !conn.vlanDown) continue;

      const FONT = '500 11px "Segoe UI", system-ui, sans-serif';
      const FONT_TAG = '600 9px "Segoe UI", system-ui, sans-serif';
      ctx.font = FONT;
      const labelW = labelText ? Math.ceil(ctx.measureText(labelText).width) : 0;

      const vlanTags = [];
      if (conn.vlanUp) vlanTags.push(conn.vlanUp);
      if (conn.vlanDown) vlanTags.push(conn.vlanDown);
      let vlanW = 0;
      if (vlanTags.length > 0) {
        ctx.font = FONT_TAG;
        for (const t of vlanTags) {
          vlanW += Math.ceil(ctx.measureText(t).width) + 16;
        }
      }
      const contentW = Math.max(labelW, vlanW);
      const totalW = contentW + 5 * 2 + 8;
      const totalH = 22;

      const bx = lx - totalW / 2;
      const by = ly - totalH / 2;
      if (x >= bx && x <= bx + totalW && y >= by && y <= by + totalH) return conn;
    }
    return null;
  }

  canvas.addEventListener('mousedown', e => {
    const pos = getCanvasPos(e);
    const d = deviceAt(pos.x, pos.y);

    if (mode === 'select') {
      const lbl = labelAt(pos.x, pos.y);
      if (lbl) {
        selectedConnection = lbl;
        selectedDevice = null;
        draggingLabel = lbl;
        canvas.style.cursor = 'grabbing';
        updateProperties();
        draw();
        return;
      }
      if (d) {
        selectedDevice = d;
        selectedConnection = null;
        draggingDevice = d;
        dragOffset = { x: pos.x - d.x, y: pos.y - d.y };
        canvas.style.cursor = 'grabbing';
      } else {
        const conn = connectionAt(pos.x, pos.y);
        if (conn) {
          selectedConnection = conn;
          selectedDevice = null;
        } else {
          selectedDevice = null;
          selectedConnection = null;
        }
      }
      updateProperties();
      draw();
    } else if (mode === 'connect') {
      if (d) {
        if (!connectStart) {
          connectStart = d.id;
        } else if (connectStart !== d.id) {
          const exists = connections.some(c =>
            (c.from === connectStart && c.to === d.id) ||
            (c.from === d.id && c.to === connectStart)
          );
          if (!exists) {
            connections.push({ from: connectStart, to: d.id, label: '', vlanUp: '', vlanDown: '', cableType: 'unknown', portA: '', portB: '' });
          }
          connectStart = null;
          draw();
        }
      } else {
        const conn = connectionAt(pos.x, pos.y);
        if (conn) {
          selectedConnection = conn;
          selectedDevice = null;
          updateProperties();
          draw();
        } else {
          connectStart = null;
          draw();
        }
      }
    }
  });

  canvas.addEventListener('mousemove', e => {
    const pos = getCanvasPos(e);
    mousePos = pos;

    if (draggingLabel) {
      draggingLabel.labelOffset = { x: pos.x, y: pos.y };
      draw();
      return;
    }

    if (draggingDevice) {
      draggingDevice.x = snapToGrid(pos.x - dragOffset.x);
      draggingDevice.y = snapToGrid(pos.y - dragOffset.y);
      draw();
      return;
    }

    const d = deviceAt(pos.x, pos.y);
    const c = d ? null : connectionAt(pos.x, pos.y);

    if (d !== hoveredDevice || c !== hoveredConnection) {
      hoveredDevice = d;
      hoveredConnection = c;
      if (mode === 'connect') {
        canvas.style.cursor = d ? 'pointer' : (c ? 'pointer' : 'crosshair');
      } else {
        canvas.style.cursor = d ? 'grab' : (c ? 'pointer' : 'default');
      }
      if (d) {
        let tipText = `${d.name} (${d.ip || 'no IP'})`;
        if (d.location) tipText += ` | ${d.location}`;
        if (d.ports && d.ports.length > 0) {
          tipText += ' | Ports: ' + d.ports.join(', ');
        }
        tooltip.textContent = tipText;
        tooltip.style.left = (pos.x + 16) + 'px';
        tooltip.style.top = (pos.y - 10) + 'px';
        tooltip.classList.remove('hidden');
      } else if (c) {
        const fromDev = devices.find(dev => dev.id === c.from);
        const toDev = devices.find(dev => dev.id === c.to);
        let tipText = `${fromDev?.name || '?'} ↔ ${toDev?.name || '?'}`;
        if (c.cableType && c.cableType !== 'unknown') tipText += ` | ${CABLE_TYPES[c.cableType]?.label || c.cableType}`;
        if (c.portA || c.portB) tipText += ` | ${c.portA || '?'} ↔ ${c.portB || '?'}`;
        tooltip.textContent = tipText;
        tooltip.style.left = (pos.x + 16) + 'px';
        tooltip.style.top = (pos.y - 10) + 'px';
        tooltip.classList.remove('hidden');
      } else {
        tooltip.classList.add('hidden');
      }
      draw();
    } else if (d) {
      tooltip.style.left = (pos.x + 16) + 'px';
      tooltip.style.top = (pos.y - 10) + 'px';
    }

    if (mode === 'connect' && connectStart) draw();
  });

  canvas.addEventListener('mouseup', () => {
    draggingDevice = null;
    draggingLabel = null;
    canvas.style.cursor = mode === 'select' ? 'default' : 'crosshair';
  });

  canvas.addEventListener('mouseleave', () => {
    draggingDevice = null;
    draggingLabel = null;
    hoveredDevice = null;
    tooltip.classList.add('hidden');
    draw();
  });

  canvas.addEventListener('dblclick', e => {
    const pos = getCanvasPos(e);
    const d = deviceAt(pos.x, pos.y);
    if (d) {
      const newName = prompt('Device name:', d.name);
      if (newName !== null && newName.trim()) {
        d.name = newName.trim();
        updateProperties();
        draw();
      }
    }
  });

  canvas.addEventListener('contextmenu', e => {
    e.preventDefault();
    const pos = getCanvasPos(e);
    const d = deviceAt(pos.x, pos.y);
    if (d) {
      if (confirm(`Delete "${d.name}"?`)) {
        deleteDevice(d.id);
      }
    }
  });

  const templates = document.querySelectorAll('.device-template');
  templates.forEach(tpl => {
    tpl.addEventListener('dragstart', e => {
      e.dataTransfer.setData('text/plain', tpl.dataset.type);
    });
  });

  canvas.addEventListener('dragover', e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });

  canvas.addEventListener('drop', e => {
    e.preventDefault();
    const type = e.dataTransfer.getData('text/plain');
    if (!type || !DEVICE_COLORS[type]) return;

    const pos = getCanvasPos(e);
    const count = devices.filter(d => d.type === type).length + 1;
    const device = {
      id: nextId++,
      type,
      name: `${DEVICE_NAMES[type]} ${count}`,
      x: snapToGrid(pos.x),
      y: snapToGrid(pos.y),
      ip: '',
      notes: '',
      ports: [],
      location: '',
      model: '',
    };
    devices.push(device);
    selectedDevice = device;
    updateProperties();
    draw();
  });

  document.getElementById('btn-save').addEventListener('click', () => {
    const data = JSON.stringify({ devices, connections, nextId }, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'network-topology.json';
    a.click();
    URL.revokeObjectURL(a.href);
  });

  document.getElementById('btn-load').addEventListener('click', () => {
    fileInput.click();
  });

  fileInput.addEventListener('change', e => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
      try {
        const data = JSON.parse(ev.target.result);
        devices = data.devices || [];
        connections = data.connections || [];
        nextId = data.nextId || devices.length + 1;
        selectedDevice = null;
        updateProperties();
        draw();
      } catch (err) {
        alert('Invalid topology file.');
      }
    };
    reader.readAsText(file);
    fileInput.value = '';
  });

  document.getElementById('btn-clear').addEventListener('click', () => {
    if (devices.length === 0 || confirm('Clear all devices and connections?')) {
      devices = [];
      connections = [];
      selectedDevice = null;
      nextId = 1;
      updateProperties();
      draw();
    }
  });

  // Topology layouts via #select-topology dropdown

  let templateSvgString = null;
  let templateImage = null;
  let templateActive = false;

  function loadTemplateSVG() {
    fetch('icons/template-background.svg')
      .then(r => r.text())
      .then(svg => {
        templateSvgString = svg;
        renderTemplate();
      });
  }

  function escHtml(v) {
    return v.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function renderTemplate() {
    if (!templateSvgString) return;
    const labels = {
      'Multi-mode Fiber': escHtml(document.getElementById('legend-mm').value),
      'Copper': escHtml(document.getElementById('legend-copper').value),
      'Single-mode Fiber': escHtml(document.getElementById('legend-sm').value),
    };
    const colors = {
      'st10': document.getElementById('legend-mm-color').value,
      'st11': document.getElementById('legend-copper-color').value,
      'st12': document.getElementById('legend-sm-color').value,
    };
    const header = escHtml(document.getElementById('legend-header').value);
    let svg = templateSvgString;

    svg = svg.replace(/>CABLE LEGEND<|>LEGEND</g, `>${header}<`);

    Object.entries(labels).forEach(([orig, val]) => {
      if (val && val !== orig) {
        const esc = orig.replace(/[.*+?^${}()|[\]\\-]/g, '\\$&');
        svg = svg.replace(new RegExp(`>${esc}<`, 'g'), () => `>${val}<`);
      }
    });

    Object.entries(colors).forEach(([cls, color]) => {
      const re = new RegExp(`(\\.${cls}\\s*\\{[^}]*stroke:)#[0-9a-fA-F]+`, 'g');
      svg = svg.replace(re, '$1' + color);
    });

    const tbFields = [
      { label: 'Rev. Time',       id: 'tb-revtime' },
      { label: 'Rev. Date',       id: 'tb-revdate' },
      { label: 'Revision',        id: 'tb-revision' },
      { label: 'Document Name',   id: 'tb-docname' },
      { label: 'Drawing Title',   id: 'tb-drawtitle' },
      { label: 'Drawn Date',      id: 'tb-drawndate' },
      { label: 'Drawn By',        id: 'tb-drawnby' },
    ];

    tbFields.forEach(({ label, id }) => {
      let val = escHtml(document.getElementById(id).value);
      if (id === 'tb-drawndate' && val) {
        const parts = val.split('-');
        if (parts.length === 3) val = `${parts[1]}/${parts[2].slice(0,2)}/${parts[0].slice(2)}`;
      } else if (id === 'tb-revdate' && val) {
        const parts = val.split('-');
        if (parts.length === 3) {
          const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
          val = `${parseInt(parts[2])} ${months[parseInt(parts[1])-1]} ${parts[0].slice(2)}`;
        }
      } else if (id === 'tb-revtime' && val) {
        const parts = val.split(':');
        if (parts.length === 2) {
          const h = parseInt(parts[0]);
          const m = parts[1];
          const ampm = h >= 12 ? 'PM' : 'AM';
          val = `${h % 12 || 12}:${m} ${ampm}`;
        }
      }
      const escaped = label.replace(/[.*+?^${}()|[\]\\-]/g, '\\$&');
      const re = new RegExp(`${escaped}:\\s*<\\/text>`);
      svg = svg.replace(re, () => `${label}:${val ? ' ' + val : ''}</text>`);
    });

    const descUpdates = [
      { field: 'Document Name', id: 'tb-docname' },
      { field: 'Drawing Title', id: 'tb-drawtitle' },
    ];
    descUpdates.forEach(({ field, id }) => {
      const val = escHtml(document.getElementById(id).value);
      const re = new RegExp(`(<desc>${field}: )[^<]*(<\\/desc>)`);
      svg = svg.replace(re, '$1' + val + '$2');
    });

    const encoded = btoa(unescape(encodeURIComponent(svg)));
    const url = 'data:image/svg+xml;base64,' + encoded;
    templateImage = new Image();
    templateImage.onload = () => { if (templateActive) draw(); };
    templateImage.src = url;
  }

  document.getElementById('btn-template').addEventListener('click', () => {
    const settings = document.getElementById('template-settings');
    if (!templateActive) {
      enableTemplate(true);
    } else {
      settings.classList.toggle('hidden');
    }
  });

  function enableTemplate(showSettings) {
    const btn = document.getElementById('btn-template');
    const settings = document.getElementById('template-settings');
    const area = canvas.closest('.canvas-area');
    if (templateActive) {
      if (showSettings) settings.classList.remove('hidden');
      return;
    }
    templateActive = true;
    btn.classList.add('active');
    if (area) area.classList.add('show-template');
    if (showSettings) settings.classList.remove('hidden');
    if (!templateSvgString) loadTemplateSVG();
    draw();
  }

  // Template settings event handlers
  const templateInputs = [
    'legend-header', 'legend-mm', 'legend-copper', 'legend-sm',
    'legend-mm-color', 'legend-copper-color', 'legend-sm-color',
    'tb-revtime', 'tb-revdate', 'tb-revision', 'tb-docname',
    'tb-drawtitle', 'tb-drawndate', 'tb-drawnby',
  ];
  templateInputs.forEach(id => {
    document.getElementById(id).addEventListener('input', renderTemplate);
  });

  ['legend-mm-color', 'legend-copper-color', 'legend-sm-color'].forEach(id => {
    document.getElementById(id).addEventListener('input', draw);
  });

  const TOPOLOGY_LAYOUTS = {
    circle(devices, w, h) {
      const cx = w / 2, cy = h / 2;
      const r = Math.min(w, h) * 0.35;
      devices.forEach((d, i) => {
        const angle = (2 * Math.PI * i) / devices.length - Math.PI / 2;
        d.x = snapToGrid(cx + r * Math.cos(angle));
        d.y = snapToGrid(cy + r * Math.sin(angle));
      });
    },

    star(devices, w, h) {
      if (devices.length < 2) return this.circle(devices, w, h);
      const cx = w / 2, cy = h / 2;
      const connCount = {};
      devices.forEach(d => { connCount[d.id] = 0; });
      connections.forEach(c => { connCount[c.from] = (connCount[c.from] || 0) + 1; connCount[c.to] = (connCount[c.to] || 0) + 1; });
      const sorted = [...devices].sort((a, b) => (connCount[b.id] || 0) - (connCount[a.id] || 0));
      const center = sorted[0];
      center.x = snapToGrid(cx);
      center.y = snapToGrid(cy);
      const others = sorted.slice(1);
      const r = Math.min(w, h) * 0.35;
      others.forEach((d, i) => {
        const angle = (2 * Math.PI * i) / others.length - Math.PI / 2;
        d.x = snapToGrid(cx + r * Math.cos(angle));
        d.y = snapToGrid(cy + r * Math.sin(angle));
      });
    },

    ring(devices, w, h) {
      this.circle(devices, w, h);
    },

    bus(devices, w, h) {
      if (devices.length < 2) return this.circle(devices, w, h);
      const margin = 100;
      const spacing = Math.min(160, (w - margin * 2) / (devices.length - 1));
      const cy = h / 2;
      const startX = (w - spacing * (devices.length - 1)) / 2;
      devices.forEach((d, i) => {
        d.x = snapToGrid(startX + i * spacing);
        d.y = snapToGrid(cy);
      });
    },

    tree(devices, w, h) {
      if (devices.length < 2) return this.circle(devices, w, h);
      const connCount = {};
      devices.forEach(d => { connCount[d.id] = 0; });
      connections.forEach(c => { connCount[c.from] = (connCount[c.from] || 0) + 1; connCount[c.to] = (connCount[c.to] || 0) + 1; });
      const sorted = [...devices].sort((a, b) => (connCount[b.id] || 0) - (connCount[a.id] || 0));
      const root = sorted[0];
      const adj = {};
      devices.forEach(d => adj[d.id] = []);
      connections.forEach(c => {
        adj[c.from].push(c.to);
        adj[c.to].push(c.from);
      });
      const visited = new Set();
      const levels = [];
      const queue = [root.id];
      visited.add(root.id);
      while (queue.length > 0) {
        const levelSize = queue.length;
        const level = [];
        for (let i = 0; i < levelSize; i++) {
          const id = queue.shift();
          level.push(id);
          for (const nb of adj[id]) {
            if (!visited.has(nb)) {
              visited.add(nb);
              queue.push(nb);
            }
          }
        }
        levels.push(level);
      }
      const placed = new Set();
      const margin = 80;
      const levelH = Math.min(120, (h - margin * 2) / Math.max(levels.length, 1));
      levels.forEach((level, li) => {
        const levelW = Math.min(140, (w - margin * 2) / Math.max(level.length, 1));
        const startX = (w - levelW * (level.length - 1)) / 2;
        level.forEach((id, i) => {
          const d = devices.find(dev => dev.id === id);
          if (d && !placed.has(id)) {
            d.x = snapToGrid(startX + i * levelW);
            d.y = snapToGrid(margin + li * levelH);
            placed.add(id);
          }
        });
      });
      const unplaced = devices.filter(d => !placed.has(d.id));
      unplaced.forEach((d, i) => {
        d.x = snapToGrid(margin + i * 140);
        d.y = snapToGrid(h - margin);
      });
    },

    grid(devices, w, h) {
      if (devices.length === 0) return;
      const cols = Math.ceil(Math.sqrt(devices.length));
      const rows = Math.ceil(devices.length / cols);
      const margin = 80;
      const cellW = (w - margin * 2) / Math.max(cols - 1, 1);
      const cellH = (h - margin * 2) / Math.max(rows - 1, 1);
      devices.forEach((d, i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        d.x = snapToGrid(margin + col * cellW);
        d.y = snapToGrid(margin + row * cellH);
      });
    },

    line(devices, w, h) {
      if (devices.length < 2) return this.circle(devices, w, h);
      const margin = 80;
      const spacing = Math.min(130, (w - margin * 2) / (devices.length - 1));
      const cy = h / 2;
      const startX = (w - spacing * (devices.length - 1)) / 2;
      devices.forEach((d, i) => {
        const stagger = (i % 2 === 0 ? -1 : 1) * 40;
        d.x = snapToGrid(startX + i * spacing);
        d.y = snapToGrid(cy + stagger);
      });
    },

    random(devices, w, h) {
      if (devices.length === 0) return;
      const margin = 80;
      devices.forEach(d => {
        d.x = snapToGrid(margin + Math.random() * (w - margin * 2));
        d.y = snapToGrid(margin + Math.random() * (h - margin * 2));
      });
    }
  };

  function applyTopology(type) {
    if (devices.length === 0) return;
    const w = canvas.width / devicePixelRatio;
    const h = canvas.height / devicePixelRatio;
    const fn = TOPOLOGY_LAYOUTS[type];
    if (fn) {
      fn(devices, w, h);
      devices.forEach(d => { delete d.labelOffset; });
      connections.forEach(c => { delete c.labelOffset; });
      draw();
    }
  }

  document.getElementById('select-topology').addEventListener('change', e => {
    if (e.target.value) {
      applyTopology(e.target.value);
      e.target.value = '';
    }
  });

  function exportCanvasAs(type) {
    draw();
    try {
      canvas.toDataURL('image/png');
    } catch (e) {
      alert('Export blocked: the canvas contains cross-origin images. Disable the Template background and try again.\n\n' + e.message);
      return;
    }
    try {
      if (type === 'jpeg') return exportJPEG();
      if (type === 'pdf') return exportPDF();
      if (type === 'svg') return exportSVG();
      if (type === 'vsdx') return exportVSDX();
    } catch (e) {
      alert('Export failed: ' + e.message);
    }
  }

  function exportJPEG() {
    canvas.toBlob(blob => {
      if (!blob) { alert('Export produced an empty image.'); return; }
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'topology.jpg';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
    }, 'image/jpeg', 0.92);
  }

  function exportPDF() {
    if (!window.jspdf) {
      alert('PDF library not loaded. Please refresh and try again.');
      return;
    }
    const w = canvas.width / devicePixelRatio;
    const h = canvas.height / devicePixelRatio;
    const imgData = canvas.toDataURL('image/png');
    const pdf = new window.jspdf.jsPDF({ orientation: 'landscape', unit: 'px', format: [w, h] });
    pdf.addImage(imgData, 'PNG', 0, 0, w, h);
    pdf.save('topology.pdf');
  }

  function exportSVG() {
    const w = canvas.width / devicePixelRatio;
    const h = canvas.height / devicePixelRatio;
    const imgData = canvas.toDataURL('image/png');
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">\n  <image href="' + imgData + '" width="' + w + '" height="' + h + '"/>\n</svg>';
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'topology.svg';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  }

  function escXml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  function exportVSDX() {
    if (typeof fflate === 'undefined') {
      alert('ZIP library not loaded. Please refresh and try again.');
      return;
    }
    const dpi = 96;
    const w = canvas.width / devicePixelRatio;
    const h = canvas.height / devicePixelRatio;
    const wIn = (w / dpi).toFixed(4);
    const hIn = (h / dpi).toFixed(4);
    const r = (DEVICE_RADIUS / dpi).toFixed(4);
    let shapeXml = '', sid = 1;

    devices.forEach(d => {
      const c = DEVICE_COLORS[d.type] || DEVICE_COLORS.pc;
      const dx = (d.x / dpi).toFixed(4);
      const dy = (d.y / dpi).toFixed(4);
      const d2 = (DEVICE_RADIUS * 2 / dpi).toFixed(4);
      const n = sid++;
      shapeXml += '<Shape ID="' + n + '" Type="Shape" Name="' + escXml(d.name) + '">';
      shapeXml += '<Section N="Geometry"><Row IX="0" T="Ellipse"><Cell N="X" V="' + r + '"/><Cell N="Y" V="' + r + '"/><Cell N="A" V="' + r + '"/><Cell N="B" V="' + r + '"/></Row></Section>';
      shapeXml += '<XForm><PinX>' + dx + '</PinX><PinY>' + dy + '</PinY><Width>' + d2 + '</Width><Height>' + d2 + '</Height><LocPinX>' + r + '</LocPinX><LocPinY>' + r + '</LocPinY></XForm>';
      shapeXml += '<Fill><Cell N="FillForegnd" V="' + c.fill + '"/><Cell N="FillPattern" V="1"/></Fill>';
      shapeXml += '<Line><Cell N="LineColor" V="' + c.stroke + '"/><Cell N="LineWidth" V="0.02"/></Line>';
      shapeXml += '<Text><cp IX="0"/><pp IX="0"/><tp IX="0"/>' + escXml(d.name) + '</Text>';
      shapeXml += '<Char IX="0"><Cell N="Size" V="0.12"/><Cell N="HorizontalAlign" V="1"/></Char>';
      shapeXml += '<Para IX="0"><Cell N="HorzAlign" V="1"/><Cell N="VertAlign" V="1"/></Para>';
      shapeXml += '</Shape>';
    });

    connections.forEach(conn => {
      const a = devices.find(d => d.id === conn.from);
      const b = devices.find(d => d.id === conn.to);
      if (!a || !b) return;
      const ax = (a.x / dpi).toFixed(4);
      const ay = (a.y / dpi).toFixed(4);
      const bx = (b.x / dpi).toFixed(4);
      const by = (b.y / dpi).toFixed(4);
      const n = sid++;
      shapeXml += '<Shape ID="' + n + '" Type="Shape" Name="Connection">';
      shapeXml += '<Section N="Geometry"><Row IX="0" T="MoveTo"><Cell N="X" V="' + ax + '"/><Cell N="Y" V="' + ay + '"/></Row><Row IX="1" T="LineTo"><Cell N="X" V="' + bx + '"/><Cell N="Y" V="' + by + '"/></Row></Section>';
      shapeXml += '<Line><Cell N="LineColor" V="#666666"/><Cell N="LineWidth" V="0.015"/></Line>';
      if (conn.label) shapeXml += '<Text><cp IX="0"/><pp IX="0"/><tp IX="0"/>' + escXml(conn.label) + '</Text>';
      shapeXml += '</Shape>';
    });

    const to = fflate.strToU8;
    const zipped = fflate.zipSync({
      '[Content_Types].xml': to(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
        '<Default Extension="xml" ContentType="application/xml"/>' +
        '<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>' +
        '<Override PartName="/visio/pages/page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>' +
        '<Override PartName="/visio/windows.xml" ContentType="application/vnd.ms-visio.windows+xml"/>' +
        '<Override PartName="/visio/theme/theme1.xml" ContentType="application/vnd.ms-visio.theme+xml"/>' +
        '</Types>'),
      '_rels/.rels': to(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="visio/document.xml"/>' +
        '</Relationships>'),
      'visio/_rels/document.xml.rels': to(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/pages" Target="pages/page1.xml"/>' +
        '<Relationship Id="rId2" Type="http://schemas.microsoft.com/office/visio/2012/relationships/windows" Target="../windows.xml"/>' +
        '<Relationship Id="rId3" Type="http://schemas.microsoft.com/office/visio/2012/relationships/theme" Target="../theme/theme1.xml"/>' +
        '</Relationships>'),
      'visio/document.xml': to(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><VisioDocument xmlns="http://schemas.microsoft.com/office/visio/2012/main">' +
        '<DocumentSheet/>' +
        '<Pages><Page ID="0" Name="Page-1"><PageSheet><PageWidth>' + wIn + '</PageWidth><PageHeight>' + hIn + '</PageHeight></PageSheet></Page></Pages>' +
        '</VisioDocument>'),
      'visio/pages/_rels/page1.xml.rels': to(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'),
      'visio/pages/page1.xml': to(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Page xmlns="http://schemas.microsoft.com/office/visio/2012/main" ID="0" Name="Page-1">' +
        '<PageSheet><PageWidth>' + wIn + '</PageWidth><PageHeight>' + hIn + '</PageHeight><PageScale>1</PageScale><DrawingScale>1 in. = 1 in.</DrawingScale></PageSheet>' +
        '<Shapes>' + shapeXml + '</Shapes>' +
        '</Page>'),
      'visio/windows.xml': to(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Windows xmlns="http://schemas.microsoft.com/office/visio/2012/main">' +
        '<Window ID="1" WindowType="Drawing" WindowState="922333440"><SheetID>0</SheetID></Window>' +
        '</Windows>'),
      'visio/theme/_rels/theme1.xml.rels': to(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'),
      'visio/theme/theme1.xml': to(
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><theme xmlns="http://schemas.microsoft.com/office/visio/2012/main"><themeElements><clrScheme name="Default"><dk1>000000</dk1><lt1>FFFFFF</lt1><dk2>44546A</dk2><lt2>E7E6E6</lt2><accent1>4472C4</accent1><accent2>ED7D31</accent2><accent3>A5A5A5</accent3><accent4>FFC000</accent4><accent5>5B9BD5</accent5><accent6>70AD47</accent6><hlink>0563C1</hlink><folHlink>954F72</folHlink></clrScheme></themeElements></theme>')
    }, { level: 9 });

    const blob = new Blob([zipped], { type: 'application/vnd.ms-visio.drawing' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'topology.vsdx';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  document.getElementById('select-export').addEventListener('change', e => {
    if (e.target.value) {
      exportCanvasAs(e.target.value);
      e.target.value = '';
    }
  });

  async function refreshLocations() {
    const panel = document.getElementById('locations-panel');
    const locations = await fetchLocations();
    if (locations.length === 0) {
      panel.innerHTML = '<p class="hint">No agents registered yet</p>';
      return;
    }
    panel.innerHTML = '';
    locations.forEach(loc => {
      const lastSeen = new Date(loc.scannedAt);
      const age = Date.now() - lastSeen.getTime();
      const dotClass = age < 600000 ? '' : (age < 3600000 ? 'stale' : 'offline');
      const timeStr = age < 60000 ? 'just now' : (age < 3600000 ? `${Math.round(age/60000)}m ago` : `${Math.round(age/3600000)}h ago`);

      const item = document.createElement('div');
      item.className = 'location-item';
      item.innerHTML = `
        <div class="location-dot ${dotClass}"></div>
        <div class="location-info">
          <div class="location-name">${loc.name || loc.id}</div>
          <div class="location-meta">${loc.deviceCount} devices | ${timeStr}</div>
        </div>
      `;
      item.addEventListener('click', () => {
        panel.querySelectorAll('.location-item').forEach(el => el.classList.remove('active'));
        item.classList.add('active');
        loadLocation(loc.id);
      });
      panel.appendChild(item);
    });
  }

  document.getElementById('btn-refresh-locations').addEventListener('click', refreshLocations);

  refreshLocations();
  setInterval(refreshLocations, 30000);

  document.getElementById('btn-discover').addEventListener('click', simulateDiscovery);

  function simulateDiscovery() {
    if (devices.length > 0 && !confirm('This will replace current topology. Continue?')) return;

    devices = [];
    connections = [];
    nextId = 1;

    const w = canvas.width / devicePixelRatio;
    const h = canvas.height / devicePixelRatio;
    const cx = w / 2;
    const cy = h / 2;

    const cloud = addDevice('cloud', 'Internet', cx, cy - 220, '0.0.0.0');
    const fw = addDevice('firewall', 'Firewall-1', cx, cy - 140, '10.0.0.1');
    const r1 = addDevice('router', 'Core-Router', cx, cy - 60, '10.0.1.1');
    const sw1 = addDevice('switch', 'Floor1-Switch', cx - 140, cy + 40, '10.0.2.1');
    const sw2 = addDevice('switch', 'Floor2-Switch', cx + 140, cy + 40, '10.0.3.1');
    const sw3 = addDevice('switch', 'Server-Switch', cx, cy + 40, '10.0.4.1');
    const ap1 = addDevice('accesspoint', 'AP-Floor1', cx - 220, cy + 140, '10.0.2.10');
    const ap2 = addDevice('accesspoint', 'AP-Floor2', cx + 220, cy + 140, '10.0.3.10');
    const s1 = addDevice('server', 'Web-Server', cx - 60, cy + 140, '10.0.4.10');
    const s2 = addDevice('server', 'DB-Server', cx + 60, cy + 140, '10.0.4.11');
    const pc1 = addDevice('pc', 'Admin-PC', cx - 220, cy + 220, '10.0.2.100');
    const pc2 = addDevice('pc', 'User-PC1', cx - 140, cy + 220, '10.0.2.101');
    const pc3 = addDevice('pc', 'User-PC2', cx + 140, cy + 220, '10.0.3.100');

    addConnection(cloud.id, fw.id, 'WAN', '', '', 'sm-fiber');
    addConnection(fw.id, r1.id, '1Gbps', '', '', 'mm-fiber');
    addConnection(r1.id, sw1.id, 'Trunk', '10,20', '10,20', 'copper');
    addConnection(r1.id, sw2.id, 'Trunk', '30,40', '30,40', 'copper');
    addConnection(r1.id, sw3.id, 'Trunk', '50,60', '50,60', 'copper');
    addConnection(sw1.id, ap1.id, 'PoE', '', '20', 'copper');
    addConnection(sw2.id, ap2.id, 'PoE', '', '40', 'copper');
    addConnection(sw3.id, s1.id, '1Gbps', '', '50', 'mm-fiber');
    addConnection(sw3.id, s2.id, '1Gbps', '', '60', 'mm-fiber');
    addConnection(sw1.id, pc1.id, '100Mbps', '', '10', 'copper');
    addConnection(sw1.id, pc2.id, '100Mbps', '', '10', 'copper');
    addConnection(sw2.id, pc3.id, '100Mbps', '', '30', 'copper');

    draw();
  }

  function addDevice(type, name, x, y, ip, location, model) {
    const d = { id: nextId++, type, name, x: snapToGrid(x), y: snapToGrid(y), ip, notes: '', location: location || '', model: model || '', ports: [] };
    devices.push(d);
    return d;
  }

  function addConnection(fromId, toId, label, vlanUp, vlanDown, cableType, portA, portB) {
    connections.push({ from: fromId, to: toId, label: label || '', vlanUp: vlanUp || '', vlanDown: vlanDown || '', cableType: cableType || 'unknown', portA: portA || '', portB: portB || '' });
  }

  // ── Real Network Scan ──

  const WORKER_API = 'https://network-mapper-api.fatannasty.workers.dev';
  const scanProgress = document.getElementById('scan-progress');
  const scanStatus = document.getElementById('scan-status');
  const scanDetail = document.getElementById('scan-detail');
  const progressFill = document.getElementById('progress-fill');
  const deviceCountEl = document.getElementById('device-count');
  let ws = null;
  let scanRunning = false;

  function updateDeviceCount() {
    if (devices.length > 0) {
      const counts = {};
      devices.forEach(d => { counts[d.type] = (counts[d.type] || 0) + 1; });
      const parts = Object.entries(counts).map(([t, c]) => `${c} ${DEVICE_NAMES[t] || t}`);
      deviceCountEl.textContent = `${devices.length} devices: ${parts.join(', ')}`;
      deviceCountEl.classList.remove('hidden');
    } else {
      deviceCountEl.classList.add('hidden');
    }
  }

  function showProgress(phase, percent, detail) {
    scanProgress.classList.remove('hidden');
    const phaseLabels = {
      arp: 'Reading ARP table...',
      ping: 'Scanning network...',
      identify: 'Identifying devices...',
      done: 'Scan complete!'
    };
    scanStatus.textContent = phaseLabels[phase] || phase;

    let pct = typeof percent === 'object' ? percent.percent : percent;
    progressFill.style.width = (pct || 0) + '%';

    if (typeof percent === 'object' && percent.scanned !== undefined) {
      scanDetail.textContent = `${percent.scanned.toLocaleString()} / ${percent.total.toLocaleString()} hosts scanned | ${percent.found} devices found`;
    } else if (detail) {
      scanDetail.textContent = detail;
    }
  }

  function hideProgress() {
    setTimeout(() => scanProgress.classList.add('hidden'), 2000);
  }

  function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}`);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'device-found' && msg.device) {
          const dev = msg.device;
          const canvasW = canvas.width / devicePixelRatio;
          const canvasH = canvas.height / devicePixelRatio;
          const idx = devices.length;
          const angle = (2 * Math.PI * idx) / 20;
          const radius = Math.min(canvasW, canvasH) * 0.35;
          const cx = canvasW / 2;
          const cy = canvasH / 2;

          const device = {
            id: nextId++,
            type: dev.type || 'pc',
            name: dev.hostname || dev.ip || `${dev.type}-${idx + 1}`,
            x: snapToGrid(cx + radius * Math.cos(angle)),
            y: snapToGrid(cy + radius * Math.sin(angle)),
            ip: dev.ip,
            mac: dev.mac || '',
            vendor: dev.vendor || '',
            notes: '',
            ports: dev.openPorts || [],
          };
          devices.push(device);
          updateDeviceCount();
          draw();
        }
      } catch (e) {}
    };

    ws.onclose = () => setTimeout(connectWebSocket, 3000);
    ws.onerror = () => {};
  }

  async function fetchLocations() {
    try {
      const res = await fetch(`${WORKER_API}/api/locations`);
      if (!res.ok) throw new Error('API unavailable');
      return await res.json();
    } catch (e) {
      return [];
    }
  }

  async function loadLocation(locationId) {
    try {
      const res = await fetch(`${WORKER_API}/api/location/${locationId}`);
      if (!res.ok) throw new Error('Not found');
      const data = await res.json();

      devices = [];
      connections = [];
      nextId = 1;

      const canvasW = canvas.width / devicePixelRatio;
      const canvasH = canvas.height / devicePixelRatio;
      const cx = canvasW / 2;
      const cy = canvasH / 2;
      const radius = Math.min(canvasW, canvasH) * 0.35;
      const excludePCs = document.getElementById('exclude-pcs').checked;
      let idx = 0;
      data.devices.forEach((dev, i) => {
        if (excludePCs && (dev.type === 'pc')) return;
        const angle = (2 * Math.PI * idx) / data.devices.length - Math.PI / 2;
        devices.push({
          id: nextId++,
          type: dev.type || 'pc',
          name: dev.hostname || dev.ip || `${dev.type}-${i + 1}`,
          x: snapToGrid(cx + radius * Math.cos(angle)),
          y: snapToGrid(cy + radius * Math.sin(angle)),
          ip: dev.ip,
          mac: dev.mac || '',
          vendor: dev.vendor || '',
          notes: '',
          ports: dev.openPorts || [],
        });
        idx++;
      });

      updateDeviceCount();
      draw();
      return data;
    } catch (e) {
      console.error('Failed to load location:', e);
      return null;
    }
  }

  async function realScan() {
    if (scanRunning) return;

    try {
      const testRes = await fetch('/api/info', { signal: AbortSignal.timeout(3000) });
      if (!testRes.ok) throw new Error('Backend not available');
    } catch (e) {
      alert('Backend server not available.\n\nTo scan your network, run:\n  npm start\n\nThen open http://localhost:7777\n\nThe Demo button works without the server.');
      return;
    }

    const cidrInput = document.getElementById('cidr-input');
    const interfaceSelect = document.getElementById('interface-select');
    let cidr = cidrInput.value.trim() || null;
    const selectedIface = interfaceSelect.value;

    if (selectedIface && !cidr) {
      try {
        const infoRes = await fetch('/api/info');
        const info = await infoRes.json();
        const iface = info.interfaces.find(i => i.name === selectedIface);
        if (iface) {
          const ipParts = iface.address.split('.').map(Number);
          const maskParts = iface.netmask.split('.').map(Number);
          const networkParts = ipParts.map((p, i) => p & maskParts[i]);
          const hostBits = maskParts.map(m => (m >>> 0).toString(2).split('1').length - 1).reduce((a, b) => a + (8 - b), 0);
          cidr = `${networkParts.join('.')}/${32 - hostBits}`;
        }
      } catch (e) {}
    }

    if (devices.length > 0 && !confirm('This will replace current topology. Continue?')) return;

    scanRunning = true;
    devices = [];
    connections = [];
    nextId = 1;
    updateDeviceCount();
    draw();

      showProgress('arp', 0, 'Starting...');
    document.getElementById('btn-scan-real').disabled = true;
    document.getElementById('btn-scan-real').textContent = 'Scanning...';

    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cidr })
      });
      const data = await res.json();

      if (data.error) {
        alert('Scan error: ' + data.error);
        return;
      }

      devices = [];
      connections = [];
      nextId = 1;

      const canvasW = canvas.width / devicePixelRatio;
      const canvasH = canvas.height / devicePixelRatio;
      const cx = canvasW / 2;
      const cy = canvasH / 2;
      const radius = Math.min(canvasW, canvasH) * 0.35;
      const total = data.devices.length;
      const excludePCs = document.getElementById('exclude-pcs').checked;
      let idx = 0;
      data.devices.forEach((dev, i) => {
        if (excludePCs && (dev.type === 'pc')) return;
        const angle = (2 * Math.PI * idx) / total - Math.PI / 2;
        const device = {
          id: nextId++,
          type: dev.type || 'pc',
          name: dev.hostname || dev.ip || `${dev.type}-${i + 1}`,
          x: snapToGrid(cx + radius * Math.cos(angle)),
          y: snapToGrid(cy + radius * Math.sin(angle)),
          ip: dev.ip,
          mac: dev.mac || '',
          vendor: dev.vendor || '',
          notes: '',
          ports: dev.openPorts || [],
        };
        devices.push(device);
        idx++;
      });

      if (data.connections) {
        data.connections.forEach(conn => {
          const fromDev = devices.find(d => d.ip === conn.from);
          const toDev = devices.find(d => d.ip === conn.to);
          if (fromDev && toDev) {
            connections.push({ from: fromDev.id, to: toDev.id, label: conn.label || '', vlanUp: conn.vlanUp || '', vlanDown: conn.vlanDown || '' });
          }
        });
      }

      showProgress('done', 100, `Found ${devices.length} devices`);
      updateDeviceCount();
      draw();
      applyTopology('circle');
      enableTemplate();
      hideProgress();

    } catch (err) {
      showProgress('done', 0, 'Error: ' + err.message);
      hideProgress();
    } finally {
      scanRunning = false;
      document.getElementById('btn-scan-real').disabled = false;
      document.getElementById('btn-scan-real').textContent = 'Scan Network';
    }
  }

  document.getElementById('btn-scan-real').addEventListener('click', realScan);

  const cidrContainer = document.getElementById('cidr-input-container');
  const cidrInput = document.getElementById('cidr-input');

  document.getElementById('btn-scan-real').addEventListener('dblclick', (e) => {
    e.preventDefault();
    cidrContainer.classList.toggle('hidden');
    if (!cidrContainer.classList.contains('hidden')) {
      fetch('/api/info').then(r => r.json()).then(info => {
        if (!cidrInput.value) cidrInput.placeholder = info.suggestedCIDR || 'e.g. 192.168.0.0/24';
        const sel = document.getElementById('interface-select');
        sel.innerHTML = '<option value="">Auto-detect</option>';
        info.interfaces.forEach(iface => {
          const opt = document.createElement('option');
          opt.value = iface.name;
          opt.textContent = `${iface.name}: ${iface.address}/${iface.netmask}`;
          sel.appendChild(opt);
        });
      });
    }
  });

  document.getElementById('btn-scan-real').addEventListener('contextmenu', (e) => {
    e.preventDefault();
    cidrContainer.classList.toggle('hidden');
  });

  cidrInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      cidrContainer.classList.add('hidden');
      realScan();
    }
  });

  const origDraw = draw;
  draw = function() {
    origDraw();
    updateDeviceCount();
  };

  // ── Catalyst Center Integration ──

  const catcUrl = document.getElementById('catc-url');
  const catcUser = document.getElementById('catc-user');
  const catcPass = document.getElementById('catc-pass');

  const savedCatc = localStorage.getItem('catc-config');
  if (savedCatc) {
    try {
      const cfg = JSON.parse(savedCatc);
      if (cfg.url) catcUrl.value = cfg.url;
      if (cfg.user) catcUser.value = cfg.user;
      if (cfg.pass) catcPass.value = cfg.pass;
    } catch {}
  }

  [catcUrl, catcUser, catcPass].forEach(el => {
    el.addEventListener('input', () => {
      localStorage.setItem('catc-config', JSON.stringify({
        url: catcUrl.value, user: catcUser.value, pass: catcPass.value
      }));
    });
  });

  document.getElementById('btn-catc-test').addEventListener('click', async () => {
    const btn = document.getElementById('btn-catc-test');
    btn.textContent = 'Testing...';
    btn.disabled = true;

    try {
      const res = await fetch('/api/catc/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: catcUrl.value, user: catcUser.value, pass: catcPass.value }),
      });
      const data = await res.json();
      if (data.success) {
        btn.textContent = `OK: ${data.deviceCount} devices`;
        btn.style.background = '#059669';
        if (data.sites && data.sites.length > 0) {
          const container = document.getElementById('catc-sites');
          container.innerHTML = '';
          const btnRow = document.createElement('div');
          btnRow.style.cssText = 'display:flex;gap:4px;margin-bottom:6px';
          const selAll = document.createElement('button');
          selAll.textContent = 'Select All';
          selAll.type = 'button';
          selAll.style.cssText = 'flex:1;font-size:11px;padding:3px 6px;border:1px solid #334155;border-radius:4px;background:#1e293b;color:#e2e8f0;cursor:pointer';
          const deselAll = document.createElement('button');
          deselAll.textContent = 'Deselect All';
          deselAll.type = 'button';
          deselAll.style.cssText = 'flex:1;font-size:11px;padding:3px 6px;border:1px solid #334155;border-radius:4px;background:#1e293b;color:#e2e8f0;cursor:pointer';
          selAll.addEventListener('click', () => { container.querySelectorAll('.catc-site-chk').forEach(cb => cb.checked = true); });
          deselAll.addEventListener('click', () => { container.querySelectorAll('.catc-site-chk').forEach(cb => cb.checked = false); });
          btnRow.appendChild(selAll);
          btnRow.appendChild(deselAll);
          container.appendChild(btnRow);
          const groups = {};
          data.sites.forEach(s => {
            const hierarchy = s.siteNameHierarchy || s.name || '';
            const parts = hierarchy.split('/');
            const region = parts.slice(0, -1).join(' > ') || 'Other';
            if (!groups[region]) groups[region] = [];
            groups[region].push(s);
          });
          for (const [region, siteList] of Object.entries(groups)) {
            const h = document.createElement('div');
            h.textContent = region;
            h.style.cssText = 'font-weight:600;font-size:12px;margin:4px 0 2px;color:#94a3b8';
            container.appendChild(h);
            siteList.forEach(s => {
              const hierarchy = s.siteNameHierarchy || s.name || s.id || '';
              const parts = hierarchy.split('/');
              const siteName = parts[parts.length - 1];
              const label = document.createElement('label');
              label.style.cssText = 'display:flex;align-items:center;gap:4px;font-size:12px;padding:2px 0';
              label.innerHTML = `<input type="checkbox" class="catc-site-chk" value="${s.id}" checked><span>${siteName}</span>`;
              container.appendChild(label);
            });
          }
          container.classList.remove('hidden');
        }
      } else {
        btn.textContent = `Error: ${data.error}`;
        btn.style.background = '#991b1b';
      }
    } catch (e) {
      btn.textContent = 'Connection failed';
      btn.style.background = '#991b1b';
    }

    btn.disabled = false;
    setTimeout(() => { btn.textContent = 'Test Connection'; btn.style.background = ''; }, 5000);
  });

  document.getElementById('btn-catc-scan').addEventListener('click', async () => {
    const btn = document.getElementById('btn-catc-scan');
    const checked = document.querySelectorAll('.catc-site-chk:checked');
    if (checked.length === 0) {
      btn.textContent = 'No sites selected';
      btn.style.background = '#d97706';
      setTimeout(() => { btn.textContent = 'Scan via Cat Center'; btn.style.background = '#059669'; }, 3000);
      return;
    }
    btn.textContent = 'Scanning...';
    btn.disabled = true;

    try {
      const res = await fetch('/api/catc/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: catcUrl.value,
          user: catcUser.value,
          pass: catcPass.value,
          siteIds: Array.from(checked).map(cb => cb.value),
        }),
      });
      const data = await res.json();
      if (data.success && data.devices && data.devices.length > 0) {
        devices = [];
        connections = [];
        nextId = 1;
        const canvasW = canvas.width / devicePixelRatio;
        const canvasH = canvas.height / devicePixelRatio;
        const cx = canvasW / 2;
        const cy = canvasH / 2;
        const radius = Math.min(canvasW, canvasH) * 0.35;
        data.devices.forEach((dev, i) => {
          const angle = (2 * Math.PI * i) / data.devices.length - Math.PI / 2;
          devices.push({
            id: nextId++,
            type: dev.type || 'switch',
            name: dev.hostname || dev.name || dev.ip || `${dev.type}-${i + 1}`,
            x: snapToGrid(cx + radius * Math.cos(angle)),
            y: snapToGrid(cy + radius * Math.sin(angle)),
            ip: dev.ip || dev.managementIpAddress || '',
            mac: dev.mac || '',
            vendor: dev.vendor || 'Cisco',
            notes: '',
            ports: [],
          });
        });
        if (data.connections) {
          data.connections.forEach(c => {
            const f = devices.find(d => d.ip === c.from || d.name === c.from);
            const t = devices.find(d => d.ip === c.to || d.name === c.to);
            if (f && t) connections.push({ from: f.id, to: t.id, label: c.label || '', vlanUp: '', vlanDown: '', cableType: 'unknown' });
          });
        }
        updateDeviceCount();
        draw();
        applyTopology('circle');
        enableTemplate();
        btn.textContent = `Done: ${devices.length} devices`;
        btn.style.background = '#059669';
      } else if (data.success) {
        btn.textContent = `No devices found (0 from ${data.locationCount || 0} sites)`;
        btn.style.background = '#d97706';
      } else {
        btn.textContent = `Error: ${data.error}`;
        btn.style.background = '#991b1b';
      }
    } catch (e) {
      btn.textContent = 'Scan failed';
      btn.style.background = '#991b1b';
    }

    btn.disabled = false;
    setTimeout(() => { btn.textContent = 'Scan via Cat Center'; btn.style.background = '#059669'; }, 5000);
  });

  // ── SSH Core Scan ──

  document.getElementById('btn-ssh-scan').addEventListener('click', async () => {
    const btn = document.getElementById('btn-ssh-scan');
    const sshHost = document.getElementById('ssh-host').value;
    const sshUser = document.getElementById('ssh-user').value;
    const sshPass = document.getElementById('ssh-pass').value;
    const sshLocation = document.getElementById('ssh-location').value;

    if (!sshHost || !sshUser || !sshPass) {
      alert('Please enter switch IP, username, and password');
      return;
    }

    btn.textContent = 'Connecting...';
    btn.disabled = true;

    try {
      const res = await fetch('/api/ssh/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: sshHost, user: sshUser, pass: sshPass, location: sshLocation }),
      });
      const data = await res.json();
      if (data.success && Array.isArray(data.devices) && data.devices.length > 0) {
        devices = [];
        connections = [];
        nextId = 1;
        const canvasW = canvas.width / devicePixelRatio;
        const canvasH = canvas.height / devicePixelRatio;
        const cx = canvasW / 2;
        const cy = canvasH / 2;
        const radius = Math.min(canvasW, canvasH) * 0.35;
        const excludePCs = document.getElementById('exclude-pcs').checked;
        let idx = 0;
        data.devices.forEach((dev, i) => {
          if (excludePCs && (dev.type === 'pc')) return;
          const angle = (2 * Math.PI * idx) / data.devices.length - Math.PI / 2;
        devices.push({
          id: nextId++,
          type: dev.type || 'pc',
          name: dev.hostname || dev.ip || `${dev.type}-${i + 1}`,
          x: snapToGrid(cx + radius * Math.cos(angle)),
          y: snapToGrid(cy + radius * Math.sin(angle)),
          ip: dev.ip,
          mac: dev.mac || '',
          vendor: dev.vendor || '',
          notes: '',
          ports: dev.openPorts || [],
        });
        idx++;
      });
        if (data.connections) {
          data.connections.forEach(conn => {
            const fromDev = devices.find(d => d.ip === conn.from);
            const toDev = devices.find(d => d.ip === conn.to);
            if (fromDev && toDev) {
              connections.push({ from: fromDev.id, to: toDev.id, label: conn.label || '', vlanUp: conn.vlanUp || '', vlanDown: conn.vlanDown || '', cableType: conn.cableType || 'unknown', portA: conn.portA || '', portB: conn.portB || '' });
            }
          });
        }
        updateDeviceCount();
        draw();
        applyTopology('circle');
        enableTemplate();
        btn.textContent = `Done: ${devices.length} devices, ${data.cdpNeighbors} neighbors`;
        btn.style.background = '#059669';
      } else if (data.success) {
        btn.textContent = `No devices found (0 from ${data.cdpNeighbors} CDP neighbors)`;
        btn.style.background = '#d97706';
      } else {
        btn.textContent = `Error: ${data.error}`;
        btn.style.background = '#991b1b';
      }
    } catch (e) {
      btn.textContent = 'Scan failed';
      btn.style.background = '#991b1b';
    }

    btn.disabled = false;
    setTimeout(() => { btn.textContent = 'Scan via SSH'; btn.style.background = '#059669'; }, 5000);
  });

  // ── Subnet Scan ──

  document.getElementById('btn-subnet-scan').addEventListener('click', async () => {
    const btn = document.getElementById('btn-subnet-scan');
    const cidr = document.getElementById('subnet-cidr').value.trim();
    const iface = document.getElementById('subnet-interface').value;

    if (!cidr) {
      alert('Please enter a subnet in CIDR notation (e.g. 192.168.1.0/24)');
      return;
    }

    if (devices.length > 0 && !confirm('This will replace current topology. Continue?')) return;

    if (scanRunning) return;

    try {
      const testRes = await fetch('/api/info', { signal: AbortSignal.timeout(3000) });
      if (!testRes.ok) throw new Error('Backend not available');
    } catch (e) {
      alert('Backend server not available.\n\nTo scan your network, run:\n  npm start\n\nThen open http://localhost:7777');
      return;
    }

    scanRunning = true;
    devices = [];
    connections = [];
    nextId = 1;
    updateDeviceCount();
    draw();

    btn.textContent = 'Scanning...';
    btn.disabled = true;

    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cidr, interface: iface || undefined })
      });
      const data = await res.json();

      if (data.error) {
        alert('Scan error: ' + data.error);
        return;
      }

      devices = [];
      connections = [];
      nextId = 1;

      const canvasW = canvas.width / devicePixelRatio;
      const canvasH = canvas.height / devicePixelRatio;
      const cx = canvasW / 2;
      const cy = canvasH / 2;
      const radius = Math.min(canvasW, canvasH) * 0.35;
      const total = data.devices.length;
      const excludePCs = document.getElementById('exclude-pcs').checked;
      let idx = 0;
      data.devices.forEach((dev, i) => {
        if (excludePCs && (dev.type === 'pc')) return;
        const angle = (2 * Math.PI * idx) / total - Math.PI / 2;
        const device = {
          id: nextId++,
          type: dev.type || 'pc',
          name: dev.hostname || dev.ip || `${dev.type}-${i + 1}`,
          x: snapToGrid(cx + radius * Math.cos(angle)),
          y: snapToGrid(cy + radius * Math.sin(angle)),
          ip: dev.ip,
          mac: dev.mac || '',
          vendor: dev.vendor || '',
          notes: '',
          ports: dev.openPorts || [],
        };
        devices.push(device);
        idx++;
      });

      if (data.connections) {
        data.connections.forEach(conn => {
          const fromDev = devices.find(d => d.ip === conn.from);
          const toDev = devices.find(d => d.ip === conn.to);
          if (fromDev && toDev) {
            connections.push({ from: fromDev.id, to: toDev.id, label: conn.label || '', vlanUp: conn.vlanUp || '', vlanDown: conn.vlanDown || '' });
          }
        });
      }

      btn.textContent = `Found ${devices.length} devices`;
      btn.style.background = '#059669';
      updateDeviceCount();
      draw();
      applyTopology('circle');
      enableTemplate();

    } catch (err) {
      btn.textContent = 'Scan failed';
      btn.style.background = '#991b1b';
    } finally {
      scanRunning = false;
      btn.disabled = false;
      setTimeout(() => { btn.textContent = 'Scan Subnet'; btn.style.background = ''; }, 3000);
    }
  });

  document.getElementById('subnet-cidr')?.addEventListener('focus', async () => {
    try {
      const res = await fetch('/api/info');
      const info = await res.json();
      const sel = document.getElementById('subnet-interface');
      sel.innerHTML = '<option value="">Auto-detect</option>';
      info.interfaces.forEach(iface => {
        const opt = document.createElement('option');
        opt.value = iface.name;
        opt.textContent = `${iface.name}: ${iface.address}/${iface.netmask}`;
        sel.appendChild(opt);
      });
      const input = document.getElementById('subnet-cidr');
      if (!input.value && info.suggestedCIDR) input.placeholder = info.suggestedCIDR;
    } catch (e) {}
  });

  connectWebSocket();

  loadIcons();
  loadModelIcons();

  window.addEventListener('resize', resizeCanvas);
  resizeCanvas();

  enableTemplate();
})();
