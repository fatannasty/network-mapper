# Network Topology Mapper

A web-based network topology diagram tool. Drag & drop devices, connect them, and visualize your network.

## Features

- **Drag & drop** network devices (routers, switches, access points, firewalls, servers, PCs, clouds)
- **Connect devices** with labeled links
- **Device properties** - name, IP address, type, notes
- **Simulate discovery** - auto-generate a sample network topology
- **Save/Load** topologies as JSON files
- **Auto Layout** - arrange devices in a circle
- Dark theme, responsive canvas

## Usage

Open `index.html` in any modern browser. No server required.

1. **Drag** a device from the sidebar onto the canvas
2. **Switch to Connect mode** and click two devices to link them
3. **Click Discover Network** to generate a demo topology
4. **Save** your topology to a JSON file for later

## File Structure

```
network-mapper/
  index.html   - Main HTML page
  style.css    - Styles (dark theme)
  app.js       - Application logic
```
