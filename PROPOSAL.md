# Printer Interface Design Proposal

## Architecture Overview
**Hardware Abstraction Layer (HAL)** pattern with mode-agnostic web UI.

```
Web UI → Hardware Interface → Mode Implementation
```

## Core Components

### 1. Hardware Abstraction Layer
- `HardwareInterface` abstract base class
- Unified API for all hardware operations
- Web UI only knows about this interface

### 2. Mode Implementations
- **Local Mode**: Realistic simulation with timing, limits, and state
- **Connected Mode**: Real hardware control via pigpio/pyserial

### 3. Single Server Script
```bash
python server.py --mode local      # Port 5000 (development)
python server.py --mode connected  # Port 5001 (production)

# Or via environment variable
MODE=local python server.py
MODE=connected python server.py
```

## Key Benefits
- **UI Agnostic**: Web UI works identically in both modes
- **Realistic Simulation**: Local mode simulates actual hardware behavior
- **Easy Testing**: Switch modes by changing port
- **Simple Deployment**: One Python script, no Docker
- **Pi-Friendly**: Minimal resource usage

## File Structure
```
printer_interface/
├── server.py                    # Main Flask server with mode switching
├── config_local.yml             # Local mode configuration (simulated limits)
├── config_connected.yml         # Connected mode configuration (real hardware)
├── hw/
│   ├── abstract_hardware.py     # Hardware interface definition (ABC)
│   ├── local_hardware.py        # Local mode implementation (simulation)
│   ├── connected_hardware.py    # Connected mode implementation (real hardware)
│   └── hardware_factory.py      # Creates appropriate hardware instance
├── ui/
│   ├── index.html               # Main web interface
│   ├── static/js/app.js         # Frontend JavaScript (SocketIO client)
│   └── static/css/style.css     # UI styling
└── requirements.txt             # Python dependencies
```

### File Descriptions

**Core Server**
- `server.py` - Main Flask application with mode detection, routes, and SocketIO handlers

**Configuration**
- `config_local.yml` - Configuration parameters (should be identical to connected)
- `config_connected.yml` - Configuration parameters (GPIO pins, serial ports, limits)

**Hardware Layer**
- `abstract_hardware.py` - Defines common interface for all hardware operations
- `local_hardware.py` - Simulates hardware with realistic timing and state management
- `connected_hardware.py` - Controls real hardware via pigpio, pyserial, picamera2
- `hardware_factory.py` - Instantiates correct hardware implementation based on mode

**User Interface**
- `index.html` - Single-page web interface with camera preview and controls
- `app.js` - Frontend logic for SocketIO communication and UI updates
- `style.css` - Styling for camera view, control buttons, and status display

## Usage
- **Development**: Run both modes on different ports
- **Production**: Run connected mode on Pi
- **Testing**: Side-by-side comparison via browser tabs

## Implementation Requirements

### Command Sequencing & ACKs
- Single command queue per server instance (FIFO)
- Each command returns ACK object: `{id, status: pending|ok|err, message}`
- Emit `telemetry.command_ack` for UI updates
- UI displays progress and disables conflicting controls while `status == pending`
- Implement timeouts and retries for connected mode
- Local mode simulates same delays/timeouts

### Safety-First Design
- Emergency-stop handled in hardware (cut motor enable/power)
- Software emergency-stop as immediate fallback
- Test hardware-level E-Stop first (don't rely only on software)
- Hardware watchdog thread stops motion if telemetry stalls
- Fail-fast on safety violations

### Homing Policy
- Require homing on boot (connected mode)
- Block zoom moves until home is obtained
- Local mode simulates exact same homing behavior
- Clear homing status in UI

### Config Validation
- Use Pydantic for config validation
- Ensure config_local.yml and config_connected.yml share same schema
- Fail fast on missing or invalid configuration
- Prevent configuration drift between modes

### Pi Zero Constraints
- Keep preview resolution low (640x480 max)
- Avoid heavy OpenCV work on main thread
- Offload CPU work to async workers
- Use pigpio and picamera2 (Pi-optimized)
- MJPEG via libcamera-jpeg or picamera2 (2-5 fps)
- Use eventlet with Flask-SocketIO (lightweight)
- Call blocking hardware operations off eventlet loop

### Error Handling & Recovery
- Define recovery from motor driver faults, serial disconnects
- Handle pigpio daemon not running, camera failures
- Ensure pigpiod starts at boot with health checks
- Serial layer: open/close with retries, detect disconnects
- Wrap hardware calls in short timeouts with recovery steps
- Fail fast and stop all movement on critical errors

### Logging & Telemetry
- Robust rotating logs
- Telemetry at 2 Hz (Pi Zero constrained)
- Compact telemetry JSON: `{t, nozzle: {x,y,z}, zoom: {s_prime_mm, magnification, pct}, status: "idle|moving|error"}`
- Balance between responsiveness and noise
- Clear status indicators for all system states

### Camera Capture & Threading
- Run camera capture in dedicated thread/process
- Use picamera2 + mjpeg streamer
- Keep main server event loop responsive
- Offload image processing to worker thread
- Do not block SocketIO event loop

### Tests & Simulation Fidelity
- Local mode enforces same numeric limits as connected
- Simulate motor motion profiles and timing
- Inject optional faults for integration tests
- Unit tests for hardware_factory, API handlers, config validation
- Integration test: server in local mode + UI socket messages

This design ensures the web UI works identically in both modes while maintaining realistic simulation behavior and simple deployment.
