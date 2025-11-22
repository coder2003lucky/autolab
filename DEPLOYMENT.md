# Raspberry Pi Deployment Guide

## Overview

This guide explains how to deploy the printer interface server on a Raspberry Pi and access it from your laptop via Tailscale.

## Architecture

```
Laptop Browser → Tailscale Network → Raspberry Pi (Server) → Hardware
```

- **Server runs on Pi**: Flask/SocketIO server on Raspberry Pi
- **Access via Tailscale**: Laptop connects to Pi's Tailscale IP
- **Web UI streams**: Camera preview and controls via web browser

## Prerequisites

1. **Raspberry Pi Setup**:
   - Raspberry Pi OS installed
   - Tailscale installed and configured
   - SSH access via Tailscale working
   - Camera enabled (if using connected mode)

2. **Tailscale Network**:
   - Both laptop and Pi connected to same Tailscale network
   - Know your Pi's Tailscale IP or hostname

## Step 1: Transfer Code to Raspberry Pi

### Option A: Clone from GitHub (Recommended)
```bash
# On Raspberry Pi
cd ~
git clone https://github.com/coder2003lucky/autolab.git
cd autolab/printer_interface
```

### Option B: Transfer via SCP
```bash
# From your laptop
scp -r printer_interface pi@raspberrypi:~/printer_interface
```

## Step 2: Install Dependencies on Pi

```bash
# SSH into Pi
tailscale ssh pi@raspberrypi

# Navigate to project
cd ~/printer_interface  # or wherever you cloned it

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install system dependencies (if needed)
sudo apt-get update
sudo apt-get install -y python3-pigpio pigpio
```

## Step 3: Configure Tailscale Access

### Find Pi's Tailscale IP
```bash
# On Raspberry Pi
tailscale ip -4
# Example output: 100.x.x.x
```

### Test Connection from Laptop
```bash
# On your laptop
ping 100.x.x.x  # Replace with your Pi's Tailscale IP
```

## Step 4: Configure the Server

### Update config_connected.yml
Edit the configuration file with your hardware settings:
```bash
nano config_connected.yml
```

Key settings:
- GPIO pins for zoom control
- Serial device for printer
- Camera settings

## Step 5: Start the Server

### Manual Start (Testing)
```bash
# On Raspberry Pi
cd ~/printer_interface
source venv/bin/activate
python server.py --mode connected --host 0.0.0.0 --port 5000
```

The server will be accessible at:
- **From laptop**: `http://100.x.x.x:5000` (replace with Pi's Tailscale IP)
- **From Pi itself**: `http://localhost:5000`

### Auto-Start with systemd (Production)

Create a systemd service:

```bash
# On Raspberry Pi
sudo nano /etc/systemd/system/printer-interface.service
```

Add this content:
```ini
[Unit]
Description=Printer Interface Server
After=network.target pigpiod.service
Requires=pigpiod.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/printer_interface
Environment="PRINTER_MODE=connected"
Environment="PATH=/home/pi/printer_interface/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/pi/printer_interface/venv/bin/python server.py --mode connected --host 0.0.0.0 --port 5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable printer-interface.service
sudo systemctl start printer-interface.service
sudo systemctl status printer-interface.service
```

## Step 6: Access from Laptop

### Open in Browser
1. Find your Pi's Tailscale IP: `tailscale ip -4` (on Pi)
2. Open browser on laptop: `http://100.x.x.x:5000`
3. You should see the printer interface UI

### Using Tailscale MagicDNS
If MagicDNS is enabled, you can use:
```
http://raspberrypi:5000
```

## Network Configuration

### Firewall (if enabled)
```bash
# On Raspberry Pi, allow port 5000
sudo ufw allow 5000/tcp
```

### Tailscale Settings
- Ensure both devices are in same Tailscale network
- Check Tailscale status: `tailscale status`
- Verify connectivity: `ping` from laptop to Pi

## Troubleshooting

### Server won't start
```bash
# Check logs
journalctl -u printer-interface -f

# Check if port is in use
sudo netstat -tulpn | grep 5000

# Test manually
cd ~/printer_interface
source venv/bin/activate
python server.py --mode connected
```

### Can't access from laptop
1. **Check Tailscale connection**:
   ```bash
   # On laptop
   tailscale ping raspberrypi
   ```

2. **Check server is running**:
   ```bash
   # On Pi
   sudo systemctl status printer-interface
   ```

3. **Check firewall**:
   ```bash
   # On Pi
   sudo ufw status
   ```

4. **Test locally on Pi**:
   ```bash
   # On Pi
   curl http://localhost:5000
   ```

### Camera not working
```bash
# Enable camera
sudo raspi-config
# Navigate to: Interface Options → Camera → Enable

# Check camera
libcamera-hello --list-cameras
```

## Development Workflow

### Option 1: Develop on Laptop, Deploy to Pi
1. Make changes on laptop
2. Commit and push to GitHub
3. Pull on Pi: `git pull`
4. Restart service: `sudo systemctl restart printer-interface`

### Option 2: Direct Development on Pi
1. SSH into Pi: `tailscale ssh pi@raspberrypi`
2. Edit files directly on Pi
3. Test changes
4. Commit and push from Pi

## Security Considerations

1. **Tailscale provides encryption** - traffic is encrypted by default
2. **Firewall** - Consider restricting access if needed
3. **HTTPS** - For production, consider adding reverse proxy with SSL
4. **Authentication** - Consider adding basic auth for production use

## Quick Reference

```bash
# Start server manually
python server.py --mode connected --host 0.0.0.0 --port 5000

# Check service status
sudo systemctl status printer-interface

# View logs
sudo journalctl -u printer-interface -f

# Restart service
sudo systemctl restart printer-interface

# Find Pi's Tailscale IP
tailscale ip -4

# Test connection from laptop
curl http://100.x.x.x:5000  # Replace with Pi's IP
```

## Next Steps

1. Transfer code to Pi
2. Install dependencies
3. Configure hardware settings
4. Start server
5. Access from laptop browser via Tailscale IP
