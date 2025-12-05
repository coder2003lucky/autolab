# Printer Interface with Camera Streaming

A unified web-based interface for controlling a 3D printer gantry system with live camera monitoring and hardware abstraction.

## Features

- **Live Camera Streaming**: Real-time MJPEG video stream from Raspberry Pi camera
  - Supports Raspberry Pi HQ Camera (IMX477) with manual focus lenses
  - Configurable image quality, sharpness, and streaming resolution
  - Optimized for Arducam C-mount lenses
- **Dual Mode Operation**: 
  - **Test Mode**: Simulates all hardware behavior without sending Arduino commands
  - **Connected Mode**: Sends actual Arduino commands to real hardware
- **Gantry Control**: Move printer nozzle in X, Y, and Z axes via G-code commands
- **Emergency Stop**: Hardware and software emergency stop functionality
- **Real-time Telemetry**: Live position and status updates via WebSocket

## Quick Start

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd pi-autolab
   ```

2. **Create virtual environment** (on Raspberry Pi, use `--system-site-packages`):
   ```bash
   python3 -m venv --system-site-packages venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **On Raspberry Pi, install system packages**:
   ```bash
   sudo apt update
   sudo apt install -y python3-picamera2 python3-flask python3-libcamera
   ```

### Running the Server

**Test Mode** (simulation, no Arduino commands):
```bash
python server.py --mode test
```

**Connected Mode** (real hardware):
```bash
python server.py --mode connected
```

**Custom port and host**:
```bash
python server.py --mode test --port 5000 --host 0.0.0.0
```

Access the web interface at `http://<raspberry-pi-ip>:5000`

## Configuration

Edit the configuration files to match your hardware:

- `config_test.yml` - Test mode configuration
- `config_connected.yml` - Connected mode configuration

Key settings:
- **Camera**: Image quality, sharpness, focus settings, streaming resolution
- **Printer**: Serial device, safe limits, feedrates
- **Safety**: Emergency stop pin, power settings

### Camera Configuration

The camera settings are configured in the `camera` section of the config files:

```yaml
camera:
  # For manual focus lenses (like Arducam C-mount LN046)
  # Adjust focus by physically rotating the focus ring on the lens
  focus_distance: null  # Leave as null for physical manual focus lenses
  
  # Image quality settings
  sharpness: 2.0  # Sharpness level (0.0-16.0, default 1.0) - higher = sharper
  jpeg_quality: 85  # JPEG compression quality (1-100, default 75) - higher = better quality

stream:
  preview_width: 1920  # Stream resolution width (px)
  preview_height: 1080  # Stream resolution height (px)
  preview_fps: 15  # Frames per second
```

**Note for Manual Focus Lenses**: If you're using a manual focus lens like the Arducam C-mount LN046, you must physically adjust the focus ring on the lens itself. The `focus_distance` setting is for motorized focus lenses only and won't work with simple manual focus lenses.

## Architecture

The system uses a hardware abstraction layer (HAL) pattern:

```
Web UI → Flask Server → Hardware Interface → Mode Implementation
```

- **Test Mode**: `hw/test_hardware.py` - Simulates hardware behavior
- **Connected Mode**: `hw/connected_hardware.py` - Real hardware control via pyserial and picamera2

Both modes implement the same interface (`hw/abstract_hardware.py`), ensuring consistent behavior.

## API

### HTTP Endpoints
- `GET /` - Main web UI
- `GET /stream` - MJPEG camera stream
- `POST /capture` - Capture high-resolution image

### WebSocket Events (SocketIO)

**Commands** (client → server):
- `cmd.move_nozzle` - Move nozzle to position `{x, y, z, feedrate}`
- `cmd.move_nozzle_xy` - Move nozzle XY only `{x, y, feedrate}`
- `cmd.move_nozzle_z` - Move nozzle Z only `{z, feedrate}`
- `cmd.emergency_stop` - Emergency stop

**Telemetry** (server → client):
- `telemetry.position` - Position updates `{nozzle: {x, y, z}, status: ...}`
- `telemetry.command_ack` - Command acknowledgments `{id, status, message, timestamp}`

## Project Structure

```
pi-autolab/
├── server.py              # Main server with camera streaming
├── config_test.yml        # Test mode configuration
├── config_connected.yml   # Connected mode configuration
├── requirements.txt       # Python dependencies
├── hw/
│   ├── abstract_hardware.py    # Hardware interface definition
│   ├── test_hardware.py         # Test mode (simulation)
│   ├── connected_hardware.py    # Connected mode (real hardware)
│   └── hardware_factory.py      # Hardware factory
└── ui/
    ├── templates/
    │   └── index.html     # Web UI
    └── static/
        ├── css/
        │   └── style.css
        └── js/
            └── app.js      # Frontend JavaScript
```

## Modes Explained

### Test Mode
- **Purpose**: Development and testing without hardware
- **Behavior**: Simulates all hardware operations with realistic timing
- **Arduino Commands**: **NOT SENT** - All commands are simulated
- **Camera**: Shows test pattern (no real camera needed)
- **Use Case**: UI development, testing logic, debugging

### Connected Mode
- **Purpose**: Production use with real hardware
- **Behavior**: Sends actual G-code commands to printer via serial
- **Arduino Commands**: **SENT** - Real hardware control
- **Camera**: Real camera stream from Raspberry Pi
- **Use Case**: Actual printer control, production use

## Troubleshooting

### Serial permission denied
- Add user to dialout group: `sudo usermod -a -G dialout $USER`
- Log out and back in

## Adding Custom Stepper Motor Controls

This section explains how to add UI buttons that control stepper motors connected to an Arduino via USB.

### Overview

The system uses a three-layer architecture:
1. **Frontend (UI)**: HTML buttons and JavaScript handlers
2. **Server**: Flask-SocketIO event handlers
3. **Hardware**: Serial communication with Arduino (G-code commands)

### Step 1: Add UI Button

Add a button to `ui/templates/index.html` in the appropriate section:

```html
<div class="control-group">
    <h3>Stepper Motor Controls</h3>
    <div class="control-row">
        <button id="stepper-forward-btn" class="btn btn-primary">Move Forward</button>
        <button id="stepper-backward-btn" class="btn btn-secondary">Move Backward</button>
        <button id="stepper-stop-btn" class="btn btn-danger">Stop</button>
    </div>
</div>
```

### Step 2: Add JavaScript Handler

In `ui/static/js/app.js`, add event handlers in the `bindEvents()` method:

```javascript
// Stepper motor controls
safeBind('stepper-forward-btn', 'click', () => {
    this.sendCommand('cmd.stepper_move', { direction: 'forward', steps: 100 });
});

safeBind('stepper-backward-btn', 'click', () => {
    this.sendCommand('cmd.stepper_move', { direction: 'backward', steps: 100 });
});

safeBind('stepper-stop-btn', 'click', () => {
    this.sendCommand('cmd.stepper_stop', {});
});
```

### Step 3: Add Server-Side Handler

In `server.py`, add a SocketIO event handler in the `create_app()` function:

```python
@socketio.on('cmd.stepper_move')
def handle_stepper_move(data):
    def execute_stepper_move():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ack = loop.run_until_complete(hardware.stepper_move(
                direction=data.get('direction', 'forward'),
                steps=data.get('steps', 100)
            ))
            emit('telemetry.command_ack', {
                'id': ack.id,
                'status': ack.status.value,
                'message': ack.message,
                'timestamp': ack.timestamp
            })
        finally:
            loop.close()
    socketio.start_background_task(execute_stepper_move)

@socketio.on('cmd.stepper_stop')
def handle_stepper_stop():
    def execute_stepper_stop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            ack = loop.run_until_complete(hardware.stepper_stop())
            emit('telemetry.command_ack', {
                'id': ack.id,
                'status': ack.status.value,
                'message': ack.message,
                'timestamp': ack.timestamp
            })
        finally:
            loop.close()
    socketio.start_background_task(execute_stepper_stop)
```

### Step 4: Add Hardware Method

In `hw/connected_hardware.py`, add methods to the `ConnectedHardware` class:

```python
async def stepper_move(self, direction: str, steps: int) -> CommandAck:
    """Move stepper motor in specified direction."""
    if self.emergency_stop_active:
        return CommandAck(
            id=f"stepper_move_{int(time.time() * 1000)}",
            status=CommandStatus.ERROR,
            message="Emergency stop active",
            timestamp=time.time()
        )
    
    # Send custom G-code or M-code command to Arduino
    # Example: M100 for custom stepper control
    # Format: M100 D<direction> S<steps>
    direction_code = '1' if direction == 'forward' else '0'
    gcode = f"M100 D{direction_code} S{steps}\n"
    
    self.printer_serial.write(gcode.encode())
    
    # Wait for acknowledgment
    response = self.printer_serial.readline().decode().strip()
    if "ok" not in response.lower():
        return CommandAck(
            id=f"stepper_move_{int(time.time() * 1000)}",
            status=CommandStatus.ERROR,
            message=f"Arduino error: {response}",
            timestamp=time.time()
        )
    
    return CommandAck(
        id=f"stepper_move_{int(time.time() * 1000)}",
        status=CommandStatus.OK,
        message=f"Stepper moved {direction} {steps} steps",
        timestamp=time.time()
    )

async def stepper_stop(self) -> CommandAck:
    """Stop stepper motor immediately."""
    # Send stop command
    self.printer_serial.write(b"M101\n")  # Example stop command
    
    response = self.printer_serial.readline().decode().strip()
    if "ok" not in response.lower():
        return CommandAck(
            id=f"stepper_stop_{int(time.time() * 1000)}",
            status=CommandStatus.ERROR,
            message=f"Arduino error: {response}",
            timestamp=time.time()
        )
    
    return CommandAck(
        id=f"stepper_stop_{int(time.time() * 1000)}",
        status=CommandStatus.OK,
        message="Stepper stopped",
        timestamp=time.time()
    )
```

Also add the method to `hw/abstract_hardware.py` as an abstract method:

```python
@abstractmethod
async def stepper_move(self, direction: str, steps: int) -> CommandAck:
    """Move stepper motor in specified direction."""
    pass

@abstractmethod
async def stepper_stop(self) -> CommandAck:
    """Stop stepper motor immediately."""
    pass
```

And implement a simulation version in `hw/test_hardware.py`:

```python
async def stepper_move(self, direction: str, steps: int) -> CommandAck:
    """Simulate stepper motor movement."""
    print(f"[TEST MODE] Simulating stepper move: {direction} {steps} steps")
    await asyncio.sleep(0.1)  # Simulate movement time
    return CommandAck(
        id=f"stepper_move_{int(time.time() * 1000)}",
        status=CommandStatus.OK,
        message=f"Stepper moved {direction} {steps} steps (simulated)",
        timestamp=time.time()
    )

async def stepper_stop(self) -> CommandAck:
    """Simulate stepper motor stop."""
    print("[TEST MODE] Simulating stepper stop")
    return CommandAck(
        id=f"stepper_stop_{int(time.time() * 1000)}",
        status=CommandStatus.OK,
        message="Stepper stopped (simulated)",
        timestamp=time.time()
    )
```

### Step 5: Arduino Firmware

On your Arduino, implement handlers for the custom commands:

```cpp
// In your Arduino G-code parser
void handle_M100() {
    // M100 D<direction> S<steps>
    int direction = code_seen('D') ? code_value() : 1;
    int steps = code_seen('S') ? code_value() : 100;
    
    // Control your stepper motor here
    if (direction == 1) {
        // Move forward
        stepper.move(steps);
    } else {
        // Move backward
        stepper.move(-steps);
    }
    
    Serial.println("ok");
}

void handle_M101() {
    // Emergency stop stepper
    stepper.stop();
    Serial.println("ok");
}
```

### Notes

- **Serial Communication**: Commands are sent as G-code/M-code strings over USB serial
- **Baud Rate**: Ensure Arduino firmware matches the baud rate in `config_connected.yml` (default: 115200)
- **Command Format**: Use standard G-code format: `M###` for custom commands, `G###` for standard movements
- **Error Handling**: Always check for `"ok"` response from Arduino before considering command successful
- **Test Mode**: Implement simulation versions in `test_hardware.py` for testing without hardware
