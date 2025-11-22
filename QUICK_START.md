# Quick Start: Raspberry Pi Deployment

## TL;DR - Get Running in 5 Minutes

### On Raspberry Pi:

```bash
# 1. Clone or transfer code
cd ~
git clone https://github.com/coder2003lucky/autolab.git
cd autolab/printer_interface

# 2. Run setup script
chmod +x setup_pi.sh
./setup_pi.sh

# 3. Start server
source venv/bin/activate
python server.py --mode connected --host 0.0.0.0 --port 5000
```

### On Your Laptop:

1. **Find Pi's Tailscale IP** (on Pi):
   ```bash
   tailscale ip -4
   # Example: 100.64.1.2
   ```

2. **Open browser**:
   ```
   http://100.64.1.2:5000
   ```
   (Replace with your Pi's actual Tailscale IP)

3. **You're done!** The web UI should load.

## How It Works

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Laptop    │         │  Tailscale   │         │ Raspberry Pi│
│   Browser   │ ──────> │   Network    │ ──────> │   Server    │
│             │         │  (Encrypted) │         │             │
└─────────────┘         └──────────────┘         └─────────────┘
                                                          │
                                                          ▼
                                                   ┌─────────────┐
                                                   │  Hardware   │
                                                   │ (Printer,   │
                                                   │  Camera)    │
                                                   └─────────────┘
```

- **Server runs on Pi**: Flask server binds to `0.0.0.0:5000` (all interfaces)
- **Tailscale provides secure tunnel**: Your laptop connects via Tailscale IP
- **Web UI streams**: Camera preview and controls work through browser
- **No port forwarding needed**: Tailscale handles networking

## Common Commands

### On Pi:
```bash
# Start server
python server.py --mode connected

# Check if running
curl http://localhost:5000

# View logs (if using systemd)
sudo journalctl -u printer-interface -f
```

### On Laptop:
```bash
# Test connection
ping <pi-tailscale-ip>

# Access in browser
open http://<pi-tailscale-ip>:5000
```

## Troubleshooting

**Can't connect from laptop?**
1. Check Tailscale: `tailscale status` (on both devices)
2. Check server is running: `curl http://localhost:5000` (on Pi)
3. Check firewall: `sudo ufw status` (on Pi)

**Server won't start?**
1. Check dependencies: `pip list`
2. Check camera: `libcamera-hello --list-cameras`
3. Check pigpio: `sudo systemctl status pigpiod`

See `DEPLOYMENT.md` for detailed troubleshooting.
