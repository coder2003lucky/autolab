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
    HardwareInterface, Position, ZoomState, CommandAck, 
    CommandStatus, SystemStatus, TelemetryData
)


class ConnectedHardware(HardwareInterface):
    """Connected hardware implementation for real hardware control."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.pi: Optional[pigpio.pi] = None
        self.printer_serial: Optional[serial.Serial] = None
        self.nozzle_pos = Position(0.0, 0.0, 0.0)
        self.zoom_state = ZoomState(
            s_prime_mm=config['zoom']['min_s_prime'],
            magnification=self._calculate_magnification(config['zoom']['min_s_prime']),
            percentage=0.0,
            is_homed=False,
            is_moving=False
        )
        self.nozzle_moving = False
        self.camera_streaming = False
        self.stream_url = None
        
    async def initialize(self) -> bool:
        """Initialize connected hardware."""
        try:
            # Initialize pigpio
            self.pi = pigpio.pi()
            if not self.pi.connected:
                print("ERROR: Failed to connect to pigpio daemon")
                return False
            
            # Initialize serial connection to printer
            self.printer_serial = serial.Serial(
                port=self.config['printer']['serial_device'],
                baudrate=115200,
                timeout=1
            )
            
            # Configure GPIO pins
            self._setup_gpio_pins()
            
            # Home zoom on startup
            await self.home_zoom()
            
            print("Connected hardware initialized successfully")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to initialize connected hardware: {e}")
            return False
    
    async def shutdown(self) -> bool:
        """Shutdown connected hardware."""
        try:
            if self.printer_serial and self.printer_serial.is_open:
                self.printer_serial.close()
            
            if self.pi:
                self.pi.stop()
            
            print("Connected hardware shutdown complete")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to shutdown connected hardware: {e}")
            return False
    
    def _setup_gpio_pins(self):
        """Setup GPIO pins for zoom control."""
        if not self.pi:
            return
        
        # Configure zoom control pins
        self.pi.set_mode(self.config['zoom']['step_pin'], pigpio.OUTPUT)
        self.pi.set_mode(self.config['zoom']['dir_pin'], pigpio.OUTPUT)
        self.pi.set_mode(self.config['zoom']['enable_pin'], pigpio.OUTPUT)
        self.pi.set_mode(self.config['zoom']['home_switch_pin'], pigpio.INPUT)
        self.pi.set_pull_up_down(self.config['zoom']['home_switch_pin'], pigpio.PUD_UP)
        
        # Configure emergency stop pin
        self.pi.set_mode(self.config['emergency_stop']['gpio_pin'], pigpio.INPUT)
        self.pi.set_pull_up_down(self.config['emergency_stop']['gpio_pin'], pigpio.PUD_UP)
        
        # Enable motors
        self.pi.write(self.config['zoom']['enable_pin'], 1)
    
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
        
        try:
            # Send G-code to printer
            gcode = f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f} F{feedrate}"
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
            
            # Update position
            self.nozzle_pos = Position(x, y, z)
            
            return CommandAck(
                id=f"move_nozzle_{int(time.time() * 1000)}",
                status=CommandStatus.OK,
                message="Movement completed",
                timestamp=time.time()
            )
            
        except Exception as e:
            return CommandAck(
                id=f"move_nozzle_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message=f"Serial communication error: {e}",
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
        return Position(self.nozzle_pos.x, self.nozzle_pos.y, self.nozzle_pos.z)
    
    # Zoom control methods
    async def zoom_in(self, steps: int) -> CommandAck:
        """Zoom in by specified number of steps."""
        if not self.zoom_state.is_homed:
            return CommandAck(
                id=f"zoom_in_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Zoom not homed",
                timestamp=time.time()
            )
        
        if self.emergency_stop_active:
            return CommandAck(
                id=f"zoom_in_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Emergency stop active",
                timestamp=time.time()
            )
        
        target_s_prime = self.zoom_state.s_prime_mm + (steps / self.config['zoom']['steps_per_mm'])
        if not self.check_zoom_limits(target_s_prime):
            return CommandAck(
                id=f"zoom_in_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Zoom position outside limits",
                timestamp=time.time()
            )
        
        try:
            self.zoom_state.is_moving = True
            self.system_status = SystemStatus.MOVING
            
            # Set direction
            direction = 1 if self.config['zoom']['direction_increase'] == 'away' else -1
            self.pi.write(self.config['zoom']['dir_pin'], direction > 0)
            
            # Step the motor
            for _ in range(steps):
                if self.emergency_stop_active:
                    self.zoom_state.is_moving = False
                    self.system_status = SystemStatus.EMERGENCY_STOP
                    return CommandAck(
                        id=f"zoom_in_{int(time.time() * 1000)}",
                        status=CommandStatus.ERROR,
                        message="Emergency stop during zoom",
                        timestamp=time.time()
                    )
                
                self.pi.write(self.config['zoom']['step_pin'], 1)
                await asyncio.sleep(0.001)  # Step pulse
                self.pi.write(self.config['zoom']['step_pin'], 0)
                await asyncio.sleep(0.001)  # Step delay
            
            # Update zoom state
            self.zoom_state.s_prime_mm = target_s_prime
            self.zoom_state.magnification = self._calculate_magnification(target_s_prime)
            self.zoom_state.percentage = self._calculate_zoom_percentage()
            self.zoom_state.is_moving = False
            self.system_status = SystemStatus.IDLE
            
            return CommandAck(
                id=f"zoom_in_{int(time.time() * 1000)}",
                status=CommandStatus.OK,
                message="Zoom in completed",
                timestamp=time.time()
            )
            
        except Exception as e:
            self.zoom_state.is_moving = False
            self.system_status = SystemStatus.ERROR
            return CommandAck(
                id=f"zoom_in_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message=f"GPIO error: {e}",
                timestamp=time.time()
            )
    
    async def zoom_out(self, steps: int) -> CommandAck:
        """Zoom out by specified number of steps."""
        return await self.zoom_in(-steps)  # Reuse zoom_in with negative steps
    
    async def home_zoom(self) -> CommandAck:
        """Home the zoom actuator."""
        if self.emergency_stop_active:
            return CommandAck(
                id=f"home_zoom_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Emergency stop active",
                timestamp=time.time()
            )
        
        try:
            self.zoom_state.is_moving = True
            self.system_status = SystemStatus.HOMING
            
            # Check if already at home
            if self.pi.read(self.config['zoom']['home_switch_pin']) == 0:
                self.zoom_state.s_prime_mm = self.config['zoom']['min_s_prime']
                self.zoom_state.percentage = 0.0
                self.zoom_state.is_homed = True
                self.zoom_state.is_moving = False
                self.system_status = SystemStatus.IDLE
                
                return CommandAck(
                    id=f"home_zoom_{int(time.time() * 1000)}",
                    status=CommandStatus.OK,
                    message="Already at home",
                    timestamp=time.time()
                )
            
            # Move towards home
            direction = -1 if self.config['zoom']['direction_increase'] == 'away' else 1
            self.pi.write(self.config['zoom']['dir_pin'], direction > 0)
            
            # Step until home switch is triggered
            max_steps = int((self.config['zoom']['max_s_prime'] - self.config['zoom']['min_s_prime']) * self.config['zoom']['steps_per_mm'])
            steps_taken = 0
            
            while self.pi.read(self.config['zoom']['home_switch_pin']) != 0 and steps_taken < max_steps:
                if self.emergency_stop_active:
                    self.zoom_state.is_moving = False
                    self.system_status = SystemStatus.EMERGENCY_STOP
                    return CommandAck(
                        id=f"home_zoom_{int(time.time() * 1000)}",
                        status=CommandStatus.ERROR,
                        message="Emergency stop during homing",
                        timestamp=time.time()
                    )
                
                self.pi.write(self.config['zoom']['step_pin'], 1)
                await asyncio.sleep(0.001)
                self.pi.write(self.config['zoom']['step_pin'], 0)
                await asyncio.sleep(0.001)
                steps_taken += 1
            
            if steps_taken >= max_steps:
                self.zoom_state.is_moving = False
                self.system_status = SystemStatus.ERROR
                return CommandAck(
                    id=f"home_zoom_{int(time.time() * 1000)}",
                    status=CommandStatus.ERROR,
                    message="Homing timeout - switch not found",
                    timestamp=time.time()
                )
            
            # Set home position
            self.zoom_state.s_prime_mm = self.config['zoom']['min_s_prime']
            self.zoom_state.magnification = self._calculate_magnification(self.zoom_state.s_prime_mm)
            self.zoom_state.percentage = 0.0
            self.zoom_state.is_homed = True
            self.zoom_state.is_moving = False
            self.system_status = SystemStatus.IDLE
            
            return CommandAck(
                id=f"home_zoom_{int(time.time() * 1000)}",
                status=CommandStatus.OK,
                message="Zoom homed successfully",
                timestamp=time.time()
            )
            
        except Exception as e:
            self.zoom_state.is_moving = False
            self.system_status = SystemStatus.ERROR
            return CommandAck(
                id=f"home_zoom_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message=f"Homing error: {e}",
                timestamp=time.time()
            )
    
    async def get_zoom_state(self) -> ZoomState:
        """Get current zoom state."""
        return ZoomState(
            s_prime_mm=self.zoom_state.s_prime_mm,
            magnification=self.zoom_state.magnification,
            percentage=self.zoom_state.percentage,
            is_homed=self.zoom_state.is_homed,
            is_moving=self.zoom_state.is_moving
        )
    
    # Emergency stop
    async def emergency_stop(self) -> CommandAck:
        """Emergency stop all movement."""
        self.emergency_stop_active = True
        self.nozzle_moving = False
        self.zoom_state.is_moving = False
        self.system_status = SystemStatus.EMERGENCY_STOP
        
        try:
            # Disable motors immediately
            if self.pi:
                self.pi.write(self.config['zoom']['enable_pin'], 0)
            
            # Send emergency stop to printer
            if self.printer_serial and self.printer_serial.is_open:
                self.printer_serial.write(b"M112\n")  # Emergency stop G-code
            
            print("EMERGENCY STOP ACTIVATED")
            
            return CommandAck(
                id=f"emergency_stop_{int(time.time() * 1000)}",
                status=CommandStatus.OK,
                message="Emergency stop activated",
                timestamp=time.time()
            )
            
        except Exception as e:
            return CommandAck(
                id=f"emergency_stop_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message=f"Emergency stop error: {e}",
                timestamp=time.time()
            )
    
    async def clear_emergency_stop(self) -> CommandAck:
        """Clear emergency stop condition."""
        self.emergency_stop_active = False
        self.system_status = SystemStatus.IDLE
        
        try:
            # Re-enable motors
            if self.pi:
                self.pi.write(self.config['zoom']['enable_pin'], 1)
            
            print("Emergency stop cleared")
            
            return CommandAck(
                id=f"clear_emergency_stop_{int(time.time() * 1000)}",
                status=CommandStatus.OK,
                message="Emergency stop cleared",
                timestamp=time.time()
            )
            
        except Exception as e:
            return CommandAck(
                id=f"clear_emergency_stop_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message=f"Clear emergency stop error: {e}",
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
            zoom=ZoomState(
                s_prime_mm=self.zoom_state.s_prime_mm,
                magnification=self.zoom_state.magnification,
                percentage=self.zoom_state.percentage,
                is_homed=self.zoom_state.is_homed,
                is_moving=self.zoom_state.is_moving
            ),
            status=self.system_status,
            error_message=None
        )
    
    async def is_ready(self) -> bool:
        """Check if hardware is ready for commands."""
        # Check system status and emergency stop
        if self.emergency_stop_active or self.system_status in [SystemStatus.ERROR, SystemStatus.EMERGENCY_STOP]:
            return False
        
        # Check hardware connections
        if not (self.pi and self.pi.connected and self.printer_serial and self.printer_serial.is_open):
            return False
        
        # For zoom operations, also check if zoom is homed
        # Note: This is a simplified check - in practice, you might want to check
        # the specific operation type before requiring zoom to be homed
        return True
    
    # Safety and limits
    def check_nozzle_limits(self, x: float, y: float, z: float) -> bool:
        """Check if nozzle position is within safe limits."""
        limits = self.config['printer']['safe_limits']
        return (limits['x_min'] <= x <= limits['x_max'] and 
                limits['y_min'] <= y <= limits['y_max'] and
                limits['z_min'] <= z <= limits['z_max'])
    
    def check_zoom_limits(self, s_prime_mm: float) -> bool:
        """Check if zoom position is within safe limits."""
        return (self.config['zoom']['min_s_prime'] <= s_prime_mm <= self.config['zoom']['max_s_prime'])
    
    def _calculate_magnification(self, s_prime_mm: float) -> float:
        """Calculate magnification from s_prime distance."""
        f = self.config['lens']['focal_length']
        return (s_prime_mm / f) - 1
    
    def _calculate_zoom_percentage(self) -> float:
        """Calculate zoom percentage based on magnification."""
        f = self.config['lens']['focal_length']
        s_prime = self.zoom_state.s_prime_mm
        
        # Calculate current magnification: M = s'/f - 1
        current_magnification = (s_prime / f) - 1
        
        # Calculate min and max possible magnifications
        min_s = self.config['zoom']['min_s_prime']
        max_s = self.config['zoom']['max_s_prime']
        min_magnification = (min_s / f) - 1
        max_magnification = (max_s / f) - 1
        
        # Calculate percentage of magnification range
        if max_magnification > min_magnification:
            return ((current_magnification - min_magnification) / (max_magnification - min_magnification)) * 100
        else:
            return 0.0
