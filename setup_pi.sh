#!/bin/bash
# Setup script for Raspberry Pi deployment

set -e

echo "=== Printer Interface Raspberry Pi Setup ==="
echo ""

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ] || ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    echo "Warning: This script is designed for Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "Found Python $PYTHON_VERSION"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created"
else
    echo "Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Check for system dependencies
echo ""
echo "Checking system dependencies..."

# Check pigpio
if ! command -v pigpiod &> /dev/null; then
    echo "Warning: pigpiod not found. Install with: sudo apt-get install pigpio"
fi

# Check camera
if [ -d "/dev/video0" ] || [ -d "/dev/video1" ]; then
    echo "Camera device found"
else
    echo "Warning: Camera device not found. Enable camera in raspi-config"
fi

# Get Tailscale IP
echo ""
echo "=== Network Information ==="
if command -v tailscale &> /dev/null; then
    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "Not connected")
    echo "Tailscale IP: $TAILSCALE_IP"
    echo ""
    echo "Access the server at: http://$TAILSCALE_IP:5000"
else
    echo "Tailscale not found. Install from: https://tailscale.com/download"
fi

# Create systemd service file
echo ""
echo "=== Systemd Service ==="
read -p "Create systemd service for auto-start? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SERVICE_FILE="/etc/systemd/system/printer-interface.service"
    CURRENT_DIR=$(pwd)
    VENV_PYTHON="$CURRENT_DIR/venv/bin/python"
    
    sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Printer Interface Server
After=network.target pigpiod.service
Requires=pigpiod.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$CURRENT_DIR
Environment="PRINTER_MODE=connected"
Environment="PATH=$CURRENT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_PYTHON server.py --mode connected --host 0.0.0.0 --port 5000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    echo "Service file created at $SERVICE_FILE"
    echo ""
    echo "To enable and start the service:"
    echo "  sudo systemctl enable printer-interface.service"
    echo "  sudo systemctl start printer-interface.service"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start the server manually:"
echo "  source venv/bin/activate"
echo "  python server.py --mode connected --host 0.0.0.0 --port 5000"
echo ""
echo "To access from your laptop:"
if [ ! -z "$TAILSCALE_IP" ] && [ "$TAILSCALE_IP" != "Not connected" ]; then
    echo "  http://$TAILSCALE_IP:5000"
else
    echo "  http://<pi-tailscale-ip>:5000"
fi
echo ""
