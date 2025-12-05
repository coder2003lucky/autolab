"""
Connected hardware implementation for real hardware control.

Controls actual hardware via pigpio, pyserial, and picamera2.
"""

import asyncio
import time
import serial
import pigpio
from typing import Dict, Any, Optional
from .abstract_hardware import (
    HardwareInterface, Position, CommandAck, 
    CommandStatus, SystemStatus, TelemetryData
)


class ConnectedHardware(HardwareInterface):
    """Connected hardware implementation for real hardware control."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.pi: Optional[pigpio.pi] = None
        self.printer_serial: Optional[serial.Serial] = None
        self.nozzle_pos = Position(0.0, 0.0, 0.0)
        self.nozzle_moving = False
        self.camera_streaming = False
        self.stream_url = None
        
    async def initialize(self) -> bool:
        """Initialize connected hardware."""
        # Initialize pigpio
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("Failed to connect to pigpio daemon")
        
        # Initialize serial connection to printer
        self.printer_serial = serial.Serial(
            port=self.config['printer']['serial_device'],
            baudrate=self.config['printer'].get('baud_rate', 115200),
            timeout=1
        )
        
        # Wait for printer to wake up
        time.sleep(2)
        
        # FORCE SAFE MODES
        self.printer_serial.write(b"G21\n")  # Set units to Millimeters
        self.printer_serial.write(b"G90\n")  # Set to Absolute Positioning
        
        # Wait for commands to be processed
        time.sleep(1)
        
        # Automatically home the nozzle on initialization
        # Note: This may take 30-60 seconds depending on printer
        print("Homing nozzle to origin (0, 0, 0)...")
        print("(This may take 30-60 seconds - please wait...)")
        ack = await self.home_nozzle()
        if ack.status != CommandStatus.OK:
            print(f"WARNING: Homing failed during initialization: {ack.message}")
            print("Server will continue, but nozzle may not be at origin. You can manually home later.")
            # Don't raise error - allow server to start even if homing fails
            # The user can manually home if needed
        else:
            print("Nozzle homed successfully")
        
        # Configure GPIO pins (if needed for other features)
        return True
    
    async def shutdown(self) -> bool:
        """Shutdown connected hardware."""
        if self.printer_serial and self.printer_serial.is_open:
            self.printer_serial.close()
        if self.pi:
            self.pi.stop()
        return True
    
    def _setup_gpio_pins(self):
        """Setup GPIO pins."""
        # Configure emergency stop pin
        self.pi.set_mode(self.config['emergency_stop']['gpio_pin'], pigpio.INPUT)
        self.pi.set_pull_up_down(self.config['emergency_stop']['gpio_pin'], pigpio.PUD_UP)
    
    # Nozzle control methods
    async def move_nozzle(self, x: float, y: float, z: float, feedrate: int) -> CommandAck:
        """Move printer nozzle to specified position."""
        if not self.check_nozzle_limits(x, y, z):
            return CommandAck(
                id=f"move_nozzle_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Position outside safe limits",
                timestamp=time.time()
            )
        
        if self.emergency_stop_active:
            return CommandAck(
                id=f"move_nozzle_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Emergency stop active",
                timestamp=time.time()
            )
        
        # Send G-code to printer
        # NOTE: If your printer has Y and Z axes physically swapped, swap them here
        # The printer firmware expects Y and Z in a certain order based on how motors are wired
        # If Y button moves Z axis and vice versa, swap y and z in the G-code command
        # For now, we'll add a config option to handle this
        swap_yz = self.config.get('printer', {}).get('swap_yz_axes', False)
        
        if swap_yz:
            # Swap Y and Z when sending to printer (hardware has them swapped)
            gcode = f"G1 X{x:.3f} Y{z:.3f} Z{y:.3f} F{feedrate}"
            # Store position correctly in our coordinate system
            self.nozzle_pos = Position(x, y, z)
        else:
            # Normal operation - no swap
            gcode = f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f} F{feedrate}"
            self.nozzle_pos = Position(x, y, z)
        
        self.printer_serial.write(f"{gcode}\n".encode())
        
        # Wait for acknowledgment
        response = self.printer_serial.readline().decode().strip()
        if "ok" not in response.lower():
            return CommandAck(
                id=f"move_nozzle_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message=f"Printer error: {response}",
                timestamp=time.time()
            )
        
        return CommandAck(
            id=f"move_nozzle_{int(time.time() * 1000)}",
            status=CommandStatus.OK,
            message="Movement completed",
            timestamp=time.time()
        )
    
    async def move_nozzle_xy(self, x: float, y: float, feedrate: int) -> CommandAck:
        """Move printer nozzle XY only (Z unchanged)."""
        return await self.move_nozzle(x, y, self.nozzle_pos.z, feedrate)
    
    async def move_nozzle_z(self, z: float, feedrate: int) -> CommandAck:
        """Move printer nozzle Z only (XY unchanged)."""
        return await self.move_nozzle(self.nozzle_pos.x, self.nozzle_pos.y, z, feedrate)
    
    async def get_nozzle_position(self) -> Position:
        """Get current nozzle position."""
        # In a real implementation, this would query the printer for current position
        # For now, return the last known position
        # Position is always stored correctly in our coordinate system (x, y, z)
        # regardless of how it's sent to the printer
        return Position(self.nozzle_pos.x, self.nozzle_pos.y, self.nozzle_pos.z)
    
    async def home_nozzle(self) -> CommandAck:
        """Home the nozzle to origin (0, 0, 0)."""
        if self.emergency_stop_active:
            return CommandAck(
                id=f"home_nozzle_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Emergency stop active",
                timestamp=time.time()
            )
        
        # Send G28 (home all axes) command to printer
        self.printer_serial.write(b"G28\n")
        
        # Homing can take 30+ seconds, so we need to read multiple responses
        # Keep reading until we get "ok" or timeout after reasonable time
        max_wait_time = 60  # 60 seconds max for homing
        start_time = time.time()
        homing_complete = False
        
        while (time.time() - start_time) < max_wait_time:
            try:
                # Use a shorter timeout per readline, but keep trying
                response = self.printer_serial.readline().decode().strip()
                if response:
                    if "ok" in response.lower():
                        homing_complete = True
                        break
                    # Printer might send status updates during homing, continue reading
            except Exception as e:
                # If readline times out, continue waiting
                await asyncio.sleep(0.1)
                continue
        
        if not homing_complete:
            return CommandAck(
                id=f"home_nozzle_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Homing timeout - printer did not respond within 60 seconds",
                timestamp=time.time()
            )
        
        # Update position to origin
        self.nozzle_pos = Position(0.0, 0.0, 0.0)
        
        return CommandAck(
            id=f"home_nozzle_{int(time.time() * 1000)}",
            status=CommandStatus.OK,
            message="Homing completed",
            timestamp=time.time()
        )
    
    # Emergency stop
    async def emergency_stop(self) -> CommandAck:
        """Emergency stop all movement."""
        self.emergency_stop_active = True
        self.nozzle_moving = False
        self.system_status = SystemStatus.EMERGENCY_STOP
        
        # Send emergency stop to printer
        self.printer_serial.write(b"M112\n")  # Emergency stop G-code
        
        return CommandAck(
            id=f"emergency_stop_{int(time.time() * 1000)}",
            status=CommandStatus.OK,
            message="Emergency stop activated",
            timestamp=time.time()
        )
    
    async def clear_emergency_stop(self) -> CommandAck:
        """Clear emergency stop condition."""
        self.emergency_stop_active = False
        self.system_status = SystemStatus.IDLE
        
        return CommandAck(
            id=f"clear_emergency_stop_{int(time.time() * 1000)}",
            status=CommandStatus.OK,
            message="Emergency stop cleared",
            timestamp=time.time()
        )
    
    # Camera methods
    async def start_camera_stream(self) -> str:
        """Start camera preview stream."""
        if not self.camera_streaming:
            self.stream_url = f"http://localhost:5001/stream"
            self.camera_streaming = True
            print(f"Starting camera stream at {self.stream_url}")
        return self.stream_url
    
    async def stop_camera_stream(self) -> bool:
        """Stop camera preview stream."""
        self.camera_streaming = False
        self.stream_url = None
        print("Camera stream stopped")
        return True
    
    async def capture_high_res(self) -> str:
        """Capture high-resolution image."""
        if not self.camera_streaming:
            return ""
        
        # In a real implementation, this would use picamera2 to capture
        filename = f"capture_{int(time.time() * 1000)}.jpg"
        print(f"Capturing high-res image: {filename}")
        return filename
    
    # Telemetry and status
    async def get_telemetry(self) -> TelemetryData:
        """Get current system telemetry."""
        return TelemetryData(
            timestamp=time.time(),
            nozzle=Position(self.nozzle_pos.x, self.nozzle_pos.y, self.nozzle_pos.z),
            status=self.system_status,
            error_message=None
        )
    
    async def is_ready(self) -> bool:
        """Check if hardware is ready for commands."""
        if self.emergency_stop_active or self.system_status in [SystemStatus.ERROR, SystemStatus.EMERGENCY_STOP]:
            return False
        if not (self.pi and self.pi.connected and self.printer_serial and self.printer_serial.is_open):
            return False
        return True
    
    # Safety and limits
    def check_nozzle_limits(self, x: float, y: float, z: float) -> bool:
        """Check if nozzle position is within safe limits."""
        limits = self.config['printer']['safe_limits']
        return (limits['x_min'] <= x <= limits['x_max'] and 
                limits['y_min'] <= y <= limits['y_max'] and
                limits['z_min'] <= z <= limits['z_max'])
