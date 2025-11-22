"""
Local hardware implementation for simulation mode.

Simulates realistic hardware behavior with timing, limits, and state management.
"""

import asyncio
import time
import random
from typing import Dict, Any
from .abstract_hardware import (
    HardwareInterface, Position, ZoomState, CommandAck, 
    CommandStatus, SystemStatus, TelemetryData
)


class LocalHardware(HardwareInterface):
    """Local hardware implementation with realistic simulation."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
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
        """Initialize local hardware simulation."""
        print("Initializing local hardware simulation...")
        self.system_status = SystemStatus.IDLE
        return True
    
    async def shutdown(self) -> bool:
        """Shutdown local hardware simulation."""
        print("Shutting down local hardware simulation...")
        self.system_status = SystemStatus.IDLE
        return True
    
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
        
        self.nozzle_moving = True
        self.system_status = SystemStatus.MOVING
        
        # Simulate realistic movement time
        distance = ((x - self.nozzle_pos.x)**2 + (y - self.nozzle_pos.y)**2 + (z - self.nozzle_pos.z)**2)**0.5
        move_time = (distance / feedrate) * 60  # Convert to seconds
        
        # Simulate gradual movement
        steps = max(1, int(move_time * 10))  # 10 updates per second
        for i in range(steps):
            if self.emergency_stop_active:
                self.nozzle_moving = False
                self.system_status = SystemStatus.EMERGENCY_STOP
                return CommandAck(
                    id=f"move_nozzle_{int(time.time() * 1000)}",
                    status=CommandStatus.ERROR,
                    message="Emergency stop during movement",
                    timestamp=time.time()
                )
            
            progress = (i + 1) / steps
            self.nozzle_pos.x = self.nozzle_pos.x + (x - self.nozzle_pos.x) * progress
            self.nozzle_pos.y = self.nozzle_pos.y + (y - self.nozzle_pos.y) * progress
            self.nozzle_pos.z = self.nozzle_pos.z + (z - self.nozzle_pos.z) * progress
            await asyncio.sleep(0.1)
        
        self.nozzle_moving = False
        self.system_status = SystemStatus.IDLE
        
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
        
        self.zoom_state.is_moving = True
        self.system_status = SystemStatus.MOVING
        
        # Simulate realistic zoom movement time
        zoom_time = abs(steps) / (self.config['zoom']['steps_per_mm'] * 2)  # 2mm/s
        
        steps_count = max(1, int(zoom_time * 10))
        for i in range(steps_count):
            if self.emergency_stop_active:
                self.zoom_state.is_moving = False
                self.system_status = SystemStatus.EMERGENCY_STOP
                return CommandAck(
                    id=f"zoom_in_{int(time.time() * 1000)}",
                    status=CommandStatus.ERROR,
                    message="Emergency stop during zoom",
                    timestamp=time.time()
                )
            
            progress = (i + 1) / steps_count
            self.zoom_state.s_prime_mm += (steps / self.config['zoom']['steps_per_mm']) * progress / steps_count
            self.zoom_state.magnification = self._calculate_magnification(self.zoom_state.s_prime_mm)
            self.zoom_state.percentage = self._calculate_zoom_percentage()
            await asyncio.sleep(0.1)
        
        self.zoom_state.is_moving = False
        self.system_status = SystemStatus.IDLE
        
        return CommandAck(
            id=f"zoom_in_{int(time.time() * 1000)}",
            status=CommandStatus.OK,
            message="Zoom in completed",
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
        
        self.zoom_state.is_moving = True
        self.system_status = SystemStatus.HOMING
        
        # Simulate homing sequence
        print(f"Simulating: Reading home switch on GPIO {self.config['zoom']['home_switch_pin']}")
        await asyncio.sleep(0.5)  # Simulate switch detection time
        
        # Move to home position
        home_time = abs(self.zoom_state.s_prime_mm - self.config['zoom']['min_s_prime']) / 2  # 2mm/s
        steps_count = max(1, int(home_time * 10))
        
        for i in range(steps_count):
            if self.emergency_stop_active:
                self.zoom_state.is_moving = False
                self.system_status = SystemStatus.EMERGENCY_STOP
                return CommandAck(
                    id=f"home_zoom_{int(time.time() * 1000)}",
                    status=CommandStatus.ERROR,
                    message="Emergency stop during homing",
                    timestamp=time.time()
                )
            
            progress = (i + 1) / steps_count
            self.zoom_state.s_prime_mm = self.config['zoom']['min_s_prime'] + (self.zoom_state.s_prime_mm - self.config['zoom']['min_s_prime']) * (1 - progress)
            self.zoom_state.magnification = self._calculate_magnification(self.zoom_state.s_prime_mm)
            self.zoom_state.percentage = self._calculate_zoom_percentage()
            await asyncio.sleep(0.1)
        
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
        
        print("EMERGENCY STOP ACTIVATED")
        
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
        
        print("Emergency stop cleared")
        
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
            self.stream_url = f"http://localhost:5000/stream"
            self.camera_streaming = True
            print(f"Simulating camera stream at {self.stream_url}")
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
        
        # Simulate capture delay
        await asyncio.sleep(0.5)
        
        filename = f"capture_{int(time.time() * 1000)}.jpg"
        print(f"Simulating high-res capture: {filename}")
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
