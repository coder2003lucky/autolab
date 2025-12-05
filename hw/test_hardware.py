"""
Test hardware implementation for simulation mode.

Simulates realistic hardware behavior with timing, limits, and state management.
Does NOT send actual Arduino commands - only simulates the behavior.
"""

import asyncio
import time
import random
from typing import Dict, Any
from .abstract_hardware import (
    HardwareInterface, Position, CommandAck, 
    CommandStatus, SystemStatus, TelemetryData
)


class TestHardware(HardwareInterface):
    """Test hardware implementation with realistic simulation (no actual Arduino commands)."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.nozzle_pos = Position(0.0, 0.0, 0.0)
        self.nozzle_moving = False
        self.camera_streaming = False
        self.stream_url = None
        
    async def initialize(self) -> bool:
        """Initialize test hardware simulation."""
        print("Initializing test hardware simulation (no Arduino commands will be sent)...", flush=True)
        self.system_status = SystemStatus.IDLE
        
        # Automatically home the nozzle on initialization
        # Since nozzle starts at (0,0,0), this should be instant
        print("Homing nozzle to origin (0, 0, 0)...", flush=True)
        try:
            ack = await self.home_nozzle()
            if ack.status != CommandStatus.OK:
                print(f"Warning: Homing failed: {ack.message}", flush=True)
            else:
                print("Nozzle homed successfully", flush=True)
        except Exception as e:
            print(f"Warning: Homing error (continuing anyway): {e}", flush=True)
        
        return True
    
    async def shutdown(self) -> bool:
        """Shutdown test hardware simulation."""
        print("Shutting down test hardware simulation...")
        self.system_status = SystemStatus.IDLE
        return True
    
    # Nozzle control methods
    async def move_nozzle(self, x: float, y: float, z: float, feedrate: int) -> CommandAck:
        """Move printer nozzle to specified position (simulated - no Arduino command sent)."""
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
        movement_delay = self.config.get('simulation', {}).get('movement_delay', 0.1)
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
            await asyncio.sleep(movement_delay)
        
        self.nozzle_moving = False
        self.system_status = SystemStatus.IDLE
        
        print(f"[TEST MODE] Simulated nozzle movement to ({x:.2f}, {y:.2f}, {z:.2f}) - no Arduino command sent")
        
        return CommandAck(
            id=f"move_nozzle_{int(time.time() * 1000)}",
            status=CommandStatus.OK,
            message="Movement completed (simulated)",
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
    
    async def home_nozzle(self) -> CommandAck:
        """Home the nozzle to origin (0, 0, 0) - simulated."""
        if self.emergency_stop_active:
            return CommandAck(
                id=f"home_nozzle_{int(time.time() * 1000)}",
                status=CommandStatus.ERROR,
                message="Emergency stop active",
                timestamp=time.time()
            )
        
        self.nozzle_moving = True
        self.system_status = SystemStatus.MOVING
        
        # Simulate homing movement
        distance = ((self.nozzle_pos.x)**2 + (self.nozzle_pos.y)**2 + (self.nozzle_pos.z)**2)**0.5
        
        # If already at origin, skip movement simulation
        if distance < 0.01:  # Already at origin (within 0.01mm)
            self.nozzle_pos = Position(0.0, 0.0, 0.0)
            self.nozzle_moving = False
            self.system_status = SystemStatus.IDLE
            print("[TEST MODE] Nozzle already at origin - homing skipped", flush=True)
        else:
            default_feedrate = self.config.get('printer', {}).get('move_feedrate_default', 1500)
            movement_delay = self.config.get('simulation', {}).get('movement_delay', 0.1)
            move_time = (distance / default_feedrate) * 60
            steps = max(1, int(move_time * 10))
            
            for i in range(steps):
                progress = (i + 1) / steps
                self.nozzle_pos.x = self.nozzle_pos.x * (1 - progress)
                self.nozzle_pos.y = self.nozzle_pos.y * (1 - progress)
                self.nozzle_pos.z = self.nozzle_pos.z * (1 - progress)
                await asyncio.sleep(movement_delay)
            
            self.nozzle_pos = Position(0.0, 0.0, 0.0)
            self.nozzle_moving = False
            self.system_status = SystemStatus.IDLE
            print(f"[TEST MODE] Simulated nozzle homing from distance {distance:.2f}mm - no Arduino command sent")
        
        return CommandAck(
            id=f"home_nozzle_{int(time.time() * 1000)}",
            status=CommandStatus.OK,
            message="Homing completed (simulated)",
            timestamp=time.time()
        )
    
    # Emergency stop
    async def emergency_stop(self) -> CommandAck:
        """Emergency stop all movement."""
        self.emergency_stop_active = True
        self.nozzle_moving = False
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
            status=self.system_status,
            error_message=None
        )
    
    async def is_ready(self) -> bool:
        """Check if hardware is ready for commands."""
        if self.emergency_stop_active or self.system_status in [SystemStatus.ERROR, SystemStatus.EMERGENCY_STOP]:
            return False
        return True
    
    # Safety and limits
    def check_nozzle_limits(self, x: float, y: float, z: float) -> bool:
        """Check if nozzle position is within safe limits."""
        limits = self.config['printer']['safe_limits']
        return (limits['x_min'] <= x <= limits['x_max'] and 
                limits['y_min'] <= y <= limits['y_max'] and
                limits['z_min'] <= z <= limits['z_max'])
