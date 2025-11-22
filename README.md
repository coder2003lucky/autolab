# Printer Interface

A web-based interface for controlling a 3D printer with live camera monitoring and zoom capabilities.

## Features

- **Live Camera Preview**: Low-resolution MJPEG stream from HQ Camera
- **High-Resolution Capture**: On-demand full-resolution image capture
- **Nozzle Control**: Move printer nozzle in X, Y, and Z axes
- **Zoom Control**: Control camera zoom via linear actuator
- **Emergency Stop**: Hardware and software emergency stop functionality
- **Dual Modes**: Local simulation and connected hardware modes
- **Real-time Telemetry**: Live position and status updates

## Architecture

The system uses a hardware abstraction layer (HAL) pattern:

```
Web UI → Hardware Interface → Mode Implementation
```

- **Local Mode**: Realistic simulation with timing, limits, and state management
- **Connected Mode**: Real hardware control via pigpio, pyserial, and picamera2

## Installation

### Prerequisites

- Python 3.8+
- Raspberry Pi OS (for connected mode)
- HQ Camera module
- Linear actuator for zoom control
- 3D printer with serial interface

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd printer_interface
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure hardware:
```bash
# Edit config files with your hardware settings
cp config_local.yml config_my_hardware.yml
# Update GPIO pins, serial device, limits, etc.
```

## Usage

### Local Mode (Simulation)
```bash
python server.py --mode local
# Access at http://localhost:5000
```

### Connected Mode (Real Hardware)
```bash
python server.py --mode connected
# Access at http://localhost:5001
```

### Environment Variable
```bash
MODE=local python server.py
MODE=connected python server.py
```

## Configuration

Both `config_local.yml` and `config_connected.yml` should have identical values for realistic simulation.

### Key Configuration Parameters

- **Camera**: Sensor dimensions, pixel pitch, focal length
- **Zoom**: GPIO pins, steps/mm, travel limits
- **Printer**: Serial device, safe limits, feedrates
- **Safety**: Emergency stop pin, power settings

## Hardware Setup

### Required Hardware
- Raspberry Pi Zero with HQ Camera
- Linear actuator for zoom control
- Stepper motor driver (A4988/DRV8825/TMC)
- Endstop switch for zoom homing
- Emergency stop button
- 3D printer (Anycubic Kobra 2 Neo)

### GPIO Connections
- Zoom Step: GPIO 18
- Zoom Direction: GPIO 19
- Zoom Enable: GPIO 20
- Home Switch: GPIO 17
- Emergency Stop: GPIO 27

## Safety Features

- **Hardware Emergency Stop**: Cuts motor enable immediately
- **Software Limits**: Enforces safe movement boundaries
- **Homing Required**: Zoom must be homed before operation
- **Watchdog**: Stops motion if telemetry stalls

## API

### HTTP Endpoints
- `GET /` - Main UI
- `GET /stream` - MJPEG camera stream
- `POST /capture` - Capture high-resolution image

### SocketIO Messages
- `cmd.move_nozzle` - Move nozzle to position
- `cmd.move_nozzle_xy` - Move nozzle XY only
- `cmd.move_nozzle_z` - Move nozzle Z only
- `cmd.zoom` - Control zoom (in/out/home)
- `cmd.emergency_stop` - Emergency stop
- `telemetry.position` - Position updates
- `telemetry.command_ack` - Command acknowledgments

## Development

### Running Tests
```bash
pytest tests/
```

### Code Structure
```
printer_interface/
├── server.py              # Main server
├── config_local.yml       # Local mode config
├── config_connected.yml   # Connected mode config
├── hw/
│   ├── abstract_hardware.py
│   ├── local_hardware.py
│   ├── connected_hardware.py
│   └── hardware_factory.py
├── ui/
│   ├── templates/
│   └── static/
└── requirements.txt
```

## Troubleshooting

### Common Issues

1. **Pigpio not running**: Start with `sudo pigpiod`
2. **Serial permission denied**: Add user to dialout group
3. **Camera not detected**: Enable camera in raspi-config
4. **GPIO errors**: Check pin assignments and permissions

### Logs
Check system logs for detailed error information:
```bash
journalctl -u printer-interface -f
```

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
