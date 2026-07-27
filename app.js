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
  let nextId = 1;

  const GRID_SIZE = 20;
  const DEVICE_RADIUS = 24;

  const DEVICE_COLORS = {
    router:     { fill: '#3b82f6', stroke: '#1e40af', icon: 'R' },
    switch:     { fill: '#10b981', stroke: '#047857', icon: 'S' },
    accesspoint:{ fill: '#f59e0b', stroke: '#d97706', icon: 'AP' },
    firewall:   { fill: '#ef4444', stroke: '#b91c1c', icon: 'FW' },
    server:     { fill: '#8b5cf6', stroke: '#6d28d9', icon: 'SV' },
    pc:         { fill: '#6366f1', stroke: '#4338ca', icon: 'PC' },
    cloud:      { fill: '#06b6d4', stroke: '#0891b2', icon: '☁' },
  };

  const DEVICE_NAMES = {
    router: 'Router',
    switch: 'Switch',
    accesspoint: 'Access Point',
    firewall: 'Firewall',
    server: 'Server',
    pc: 'PC',
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
    ctx.strokeStyle = '#1e293b';
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
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = isSelected ? '#38bdf8' : '#475569';
      ctx.lineWidth = isSelected ? 3 : 2;
      ctx.stroke();

      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2;
      const angle = Math.atan2(b.y - a.y, b.x - a.x);
      const perpX = -Math.sin(angle) * 12;
      const perpY = Math.cos(angle) * 12;

      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      if (conn.label) {
        ctx.fillStyle = '#94a3b8';
        ctx.font = '10px sans-serif';
        ctx.fillText(conn.label, mx, my - 10);
      }

      if (conn.vlanUp) {
        ctx.fillStyle = '#f59e0b';
        ctx.font = 'bold 9px monospace';
        ctx.fillText(`VLAN ${conn.vlanUp}`, mx + perpX, my + perpY - 6);
      }
      if (conn.vlanDown) {
        ctx.fillStyle = '#10b981';
        ctx.font = 'bold 9px monospace';
        ctx.fillText(`VLAN ${conn.vlanDown}`, mx + perpX, my + perpY + 6);
      }
    });
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

    drawDeviceIcon(d.type, d.x, d.y, r, colors);

    ctx.fillStyle = '#e2e8f0';
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(d.name, d.x, d.y + r + 6);

    let yOffset = r + 20;
    if (d.ip) {
      ctx.fillStyle = '#64748b';
      ctx.font = '9px sans-serif';
      ctx.fillText(d.ip, d.x, d.y + yOffset);
      yOffset += 12;
    }

    if (d.ports && d.ports.length > 0) {
      ctx.fillStyle = '#38bdf8';
      ctx.font = '8px monospace';
      const portsStr = d.ports.join(', ');
      ctx.fillText(portsStr, d.x, d.y + yOffset);
    }

    ctx.restore();
  }

  function drawDeviceIcon(type, x, y, r, colors) {
    ctx.save();
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

  function draw() {
    const w = canvas.width / devicePixelRatio;
    const h = canvas.height / devicePixelRatio;
    ctx.clearRect(0, 0, w, h);
    drawGrid();
    drawConnections();

    if (connectStart && mode === 'connect') {
      const a = devices.find(d => d.id === connectStart);
      if (a) {
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(mousePos.x, mousePos.y);
        ctx.strokeStyle = '#38bdf8';
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
      if (dx * dx + dy * dy <= DEVICE_RADIUS * DEVICE_RADIUS) return d;
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
        <p style="font-size:11px;color:#94a3b8;margin-bottom:8px">${fromDev ? fromDev.name : '?'} ↔ ${toDev ? toDev.name : '?'}</p>
        <label>Link Label
          <input type="text" id="prop-conn-label" value="${conn.label || ''}" placeholder="e.g. Trunk, 1Gbps">
        </label>
        <label>Uplink VLAN
          <input type="text" id="prop-conn-vlanup" value="${conn.vlanUp || ''}" placeholder="e.g. 10, 20, 100">
        </label>
        <label>Downlink VLAN
          <input type="text" id="prop-conn-vlandown" value="${conn.vlanDown || ''}" placeholder="e.g. 30, 40, 200">
        </label>
        <button class="delete-btn" id="prop-conn-delete">Delete Connection</button>
      `;
      document.getElementById('prop-conn-label').addEventListener('input', e => {
        conn.label = e.target.value;
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
    propertiesPanel.innerHTML = `
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
      <label>Notes
        <input type="text" id="prop-notes" value="${d.notes || ''}" placeholder="Optional notes">
      </label>
      <label>Open Ports (comma-separated)
        <input type="text" id="prop-ports" value="${(d.ports || []).join(', ')}" placeholder="e.g. 22, 80, 443">
      </label>
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
    const threshold = 8;
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

  canvas.addEventListener('mousedown', e => {
    const pos = getCanvasPos(e);
    const d = deviceAt(pos.x, pos.y);

    if (mode === 'select') {
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
            connections.push({ from: connectStart, to: d.id, label: '', vlanUp: '', vlanDown: '' });
          }
          connectStart = null;
          draw();
        }
      } else {
        connectStart = null;
        draw();
      }
    }
  });

  canvas.addEventListener('mousemove', e => {
    const pos = getCanvasPos(e);
    mousePos = pos;

    if (draggingDevice) {
      draggingDevice.x = snapToGrid(pos.x - dragOffset.x);
      draggingDevice.y = snapToGrid(pos.y - dragOffset.y);
      draw();
      return;
    }

    const d = deviceAt(pos.x, pos.y);
    if (d !== hoveredDevice) {
      hoveredDevice = d;
      canvas.style.cursor = d ? (mode === 'select' ? 'grab' : 'pointer') : 'default';
      if (d) {
        let tipText = `${d.name} (${d.ip || 'no IP'})`;
        if (d.ports && d.ports.length > 0) {
          tipText += ' | Ports: ' + d.ports.join(', ');
        }
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
    canvas.style.cursor = mode === 'select' ? 'default' : 'crosshair';
  });

  canvas.addEventListener('mouseleave', () => {
    draggingDevice = null;
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

  document.getElementById('btn-auto-layout').addEventListener('click', autoLayout);

  function autoLayout() {
    if (devices.length === 0) return;
    const w = canvas.width / devicePixelRatio;
    const h = canvas.height / devicePixelRatio;
    const cx = w / 2;
    const cy = h / 2;
    const r = Math.min(w, h) * 0.35;

    devices.forEach((d, i) => {
      const angle = (2 * Math.PI * i) / devices.length - Math.PI / 2;
      d.x = snapToGrid(cx + r * Math.cos(angle));
      d.y = snapToGrid(cy + r * Math.sin(angle));
    });
    draw();
  }

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

    addConnection(cloud.id, fw.id, 'WAN', '', '');
    addConnection(fw.id, r1.id, '1Gbps', '', '');
    addConnection(r1.id, sw1.id, 'Trunk', '10,20', '10,20');
    addConnection(r1.id, sw2.id, 'Trunk', '30,40', '30,40');
    addConnection(r1.id, sw3.id, 'Trunk', '50,60', '50,60');
    addConnection(sw1.id, ap1.id, 'PoE', '', '20');
    addConnection(sw2.id, ap2.id, 'PoE', '', '40');
    addConnection(sw3.id, s1.id, '1Gbps', '', '50');
    addConnection(sw3.id, s2.id, '1Gbps', '', '60');
    addConnection(sw1.id, pc1.id, '100Mbps', '', '10');
    addConnection(sw1.id, pc2.id, '100Mbps', '', '10');
    addConnection(sw2.id, pc3.id, '100Mbps', '', '30');

    draw();
  }

  function addDevice(type, name, x, y, ip) {
    const d = { id: nextId++, type, name, x: snapToGrid(x), y: snapToGrid(y), ip, notes: '' };
    devices.push(d);
    return d;
  }

  function addConnection(fromId, toId, label, vlanUp, vlanDown) {
    connections.push({ from: fromId, to: toId, label: label || '', vlanUp: vlanUp || '', vlanDown: vlanDown || '' });
  }

  // ── Real Network Scan ──

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
      ping: 'Pinging hosts...',
      identify: 'Identifying devices...',
      done: 'Scan complete!'
    };
    scanStatus.textContent = phaseLabels[phase] || phase;
    progressFill.style.width = percent + '%';
    if (detail) scanDetail.textContent = detail;
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
            name: dev.hostname || `${dev.type}-${idx + 1}`,
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

  async function realScan() {
    if (scanRunning) return;
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
      const res = await fetch('/api/scan', { method: 'POST' });
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

      data.devices.forEach((dev, i) => {
        const angle = (2 * Math.PI * i) / total - Math.PI / 2;
        const device = {
          id: nextId++,
          type: dev.type || 'pc',
          name: dev.hostname || `${dev.type}-${i + 1}`,
          x: snapToGrid(cx + radius * Math.cos(angle)),
          y: snapToGrid(cy + radius * Math.sin(angle)),
          ip: dev.ip,
          mac: dev.mac || '',
          vendor: dev.vendor || '',
          notes: '',
          ports: dev.openPorts || [],
        };
        devices.push(device);
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
      autoLayout();
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

  const origDraw = draw;
  draw = function() {
    origDraw();
    updateDeviceCount();
  };

  connectWebSocket();

  window.addEventListener('resize', resizeCanvas);
  resizeCanvas();
})();
