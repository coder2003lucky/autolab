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
        self._loop = None  # Will be set to current event loop when needed
        
    def _get_loop(self):
        """Get the current event loop, creating one if necessary."""
        if self._loop is None:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop
    
    async def _run_in_executor(self, func, *args):
        """Run a blocking function in a thread executor."""
        loop = self._get_loop()
        return await loop.run_in_executor(None, func, *args)
    
    async def initialize(self) -> bool:
        """Initialize connected hardware following Anycubic Kobra 2 Neo initialization pattern."""
        # Initialize pigpio
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("Failed to connect to pigpio daemon")
        
        # Initialize serial connection to printer
        serial_port = self.config['printer']['serial_device']
        baud_rate = self.config['printer'].get('baud_rate', 115200)
        
        print(f"Connecting to {serial_port} at {baud_rate}...")
        
        # Serial.Serial() is blocking, run it in executor
        def _open_serial():
            return serial.Serial(
                port=serial_port,
                baudrate=baud_rate,
                timeout=1
            )
        
        self.printer_serial = await self._run_in_executor(_open_serial)
        
        # CRITICAL: When you open the port, the printer usually reboots (DTR reset).
        # We must wait a few seconds for it to be ready.
        # Use asyncio.sleep instead of time.sleep to avoid blocking the event loop
        print("Waiting for printer to initialize after connection (3 seconds)...")
        await asyncio.sleep(3)
        
        # Clear any startup text (like "Marlin x.x.x" or boot messages)
        # reset_input_buffer() is blocking, run it in executor
        await self._run_in_executor(self.printer_serial.reset_input_buffer)
        print("Printer connected and ready.\n")
        
        # Set safe modes: G21 (millimeters) and G90 (absolute positioning)
        print("Setting safe modes (G21: millimeters, G90: absolute positioning)...")
        ack1 = await self._send_gcode("G21")  # Set units to Millimeters
        ack2 = await self._send_gcode("G90")  # Set to Absolute Positioning
        
        if ack1.status != CommandStatus.OK or ack2.status != CommandStatus.OK:
            print(f"WARNING: Failed to set safe modes. G21: {ack1.status}, G90: {ack2.status}")
            print("Continuing anyway - printer may already be in correct mode.")
        
        # Automatically home the nozzle on initialization
        # Note: This may take 30-60 seconds depending on printer
        print("\nHoming nozzle to origin (0, 0, 0)...")
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
            # Serial.close() is blocking, run it in executor
            await self._run_in_executor(self.printer_serial.close)
        if self.pi:
            self.pi.stop()
        return True
    
    def _setup_gpio_pins(self):
        """Setup GPIO pins."""
        # Configure emergency stop pin
        self.pi.set_mode(self.config['emergency_stop']['gpio_pin'], pigpio.INPUT)
        self.pi.set_pull_up_down(self.config['emergency_stop']['gpio_pin'], pigpio.PUD_UP)
    
    async def _send_gcode(self, command: str, timeout: float = 5.0) -> CommandAck:
        """
        Send a G-code command and wait for 'ok' response.
        
        This follows the pattern from the Anycubic Kobra 2 Neo guide:
        - Send command with newline
        - Read responses until we get 'ok' or timeout
        
        All blocking serial operations are run in a thread executor to avoid
        blocking the event loop.
        
        Args:
            command: G-code command (without newline)
            timeout: Maximum time to wait for 'ok' response (seconds)
            
        Returns:
            CommandAck with status OK if 'ok' received, ERROR otherwise
        """
        if not self.printer_serial or not self.printer_serial.is_open:
            return CommandAck(
                id=f"gcode_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Printer serial port not open",
                timestamp=time.time()
            )
        
        command_id = f"gcode_{int(time.time() * 1000)}"
        start_time = time.time()
        
        # G-code must end with a newline character (\n)
        full_command = f"{command}\n"
        
        # Serial.write() is blocking, run it in executor
        def _write_command():
            self.printer_serial.write(full_command.encode('utf-8'))
        
        await self._run_in_executor(_write_command)
        
        # Read the response lines until we get 'ok' or timeout
        # Use asyncio.sleep instead of time.sleep in the loop
        while (time.time() - start_time) < timeout:
            try:
                # Serial.readline() is blocking, run it in executor
                def _read_line():
                    return self.printer_serial.readline().decode('utf-8').strip()
                
                line = await self._run_in_executor(_read_line)
                
                if line:
                    # Standard Marlin firmware replies with "ok" when done
                    if line.lower().startswith('ok'):
                        return CommandAck(
                            id=command_id,
                            status=CommandStatus.OK,
                            message=f"Command '{command}' completed",
                            timestamp=time.time()
                        )
                    # Check for error responses
                    if 'error' in line.lower() or 'resend' in line.lower():
                        return CommandAck(
                            id=command_id,
                            status=CommandStatus.ERROR,
                            message=f"Printer error: {line}",
                            timestamp=time.time()
                        )
            except Exception as e:
                # If readline times out or fails, continue waiting
                await asyncio.sleep(0.1)
                continue
        
        # Timeout - no 'ok' received
        return CommandAck(
            id=command_id,
            status=CommandStatus.ERROR,
            message=f"Timeout waiting for 'ok' response to '{command}'",
            timestamp=time.time()
        )
    
    # Nozzle control methods
    async def move_nozzle(self, x: float, y: float, z: float, feedrate: int) -> CommandAck:
        """Move printer nozzle to specified position using G1 command."""
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
            # G1 = Linear move, F = feedrate (speed)
            gcode = f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f} F{feedrate}"
            self.nozzle_pos = Position(x, y, z)
        
        # Use the helper method to send G-code and wait for 'ok'
        # Movement commands may take longer, so use a longer timeout
        ack = await self._send_gcode(gcode, timeout=30.0)
        
        if ack.status == CommandStatus.OK:
            # Update system status to moving, then back to idle
            self.system_status = SystemStatus.MOVING
            self.nozzle_moving = True
            # Note: Status will be updated to IDLE when telemetry reports idle
        
        return ack
    
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
        """Home the nozzle to origin (0, 0, 0) using G28 command."""
        if self.emergency_stop_active:
            return CommandAck(
                id=f"home_nozzle_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Emergency stop active",
                timestamp=time.time()
            )
        
        # G28 = Auto Home (moves all axes to the limit switches)
        # Homing can take 30-60 seconds, so use a longer timeout
        self.system_status = SystemStatus.HOMING
        ack = await self._send_gcode("G28", timeout=60.0)
        
        if ack.status == CommandStatus.OK:
            # Update position to origin after successful homing
            self.nozzle_pos = Position(0.0, 0.0, 0.0)
            self.system_status = SystemStatus.IDLE
            ack.message = "Homing completed"
        else:
            self.system_status = SystemStatus.ERROR
        
        return ack
    
    # Emergency stop
    async def emergency_stop(self) -> CommandAck:
        """Emergency stop all movement using M112 command."""
        self.emergency_stop_active = True
        self.nozzle_moving = False
        self.system_status = SystemStatus.EMERGENCY_STOP
        
        # M112 = Emergency stop G-code
        # Don't wait for response - emergency stop should be immediate
        if self.printer_serial and self.printer_serial.is_open:
            # Serial.write() is blocking, run it in executor
            def _write_emergency_stop():
                self.printer_serial.write(b"M112\n")
            
            await self._run_in_executor(_write_emergency_stop)
        
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
    
    async def get_temperature(self) -> Dict[str, Any]:
        """
        Query printer temperature using M105 command.
        
        Returns:
            Dict with 'nozzle_temp' and 'bed_temp' if successful, None otherwise
        """
        if not self.printer_serial or not self.printer_serial.is_open:
            return None
        
        # M105 = Report Temperature
        # Send command (blocking, run in executor)
        def _write_temp_query():
            self.printer_serial.write(b"M105\n")
        
        await self._run_in_executor(_write_temp_query)
        
        # Read response (M105 typically returns something like "ok T:25.0 /0.0 B:25.0 /0.0")
        start_time = time.time()
        while (time.time() - start_time) < 2.0:  # 2 second timeout
            try:
                # Serial.readline() is blocking, run it in executor
                def _read_temp_line():
                    return self.printer_serial.readline().decode('utf-8').strip()
                
                line = await self._run_in_executor(_read_temp_line)
                
                if line:
                    # Parse temperature from response
                    # Format is typically: "ok T:25.0 /200.0 B:60.0 /60.0"
                    # T = current nozzle temp, / = target nozzle temp
                    # B = current bed temp, / = target bed temp
                    import re
                    temp_match = re.search(r'T:([\d.]+)', line)
                    bed_match = re.search(r'B:([\d.]+)', line)
                    
                    if temp_match and bed_match:
                        return {
                            'nozzle_temp': float(temp_match.group(1)),
                            'bed_temp': float(bed_match.group(1))
                        }
                    if 'ok' in line.lower():
                        break  # Got ok but couldn't parse temps
            except Exception:
                await asyncio.sleep(0.1)
                continue
        
        return None
    
    async def get_firmware_info(self) -> Optional[str]:
        """
        Query printer firmware information using M115 command.
        
        Returns:
            Firmware info string if successful, None otherwise
        """
        if not self.printer_serial or not self.printer_serial.is_open:
            return None
        
        # M115 = Get Firmware Version and Capabilities
        # Serial.write() is blocking, run it in executor
        def _write_firmware_query():
            self.printer_serial.write(b"M115\n")
        
        await self._run_in_executor(_write_firmware_query)
        
        # Read response (may be multiple lines)
        start_time = time.time()
        info_lines = []
        while (time.time() - start_time) < 3.0:  # 3 second timeout
            try:
                # Serial.readline() is blocking, run it in executor
                def _read_firmware_line():
                    return self.printer_serial.readline().decode('utf-8').strip()
                
                line = await self._run_in_executor(_read_firmware_line)
                
                if line:
                    if 'ok' in line.lower():
                        break
                    info_lines.append(line)
            except Exception:
                await asyncio.sleep(0.1)
                continue
        
        return '\n'.join(info_lines) if info_lines else None
    
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
