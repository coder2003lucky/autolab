"""
Abstract hardware interface for printer control system.

Defines the common interface that both local and connected hardware implementations
must follow. This ensures the web UI works identically regardless of mode.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum
import time
import uuid
import asyncio
import logging
import traceback


class CommandStatus(Enum):
    """Status of a hardware command."""
    PENDING = "pending"
    OK = "ok"
    ERROR = "err"


class SystemStatus(Enum):
    """Overall system status."""
    IDLE = "idle"
    MOVING = "moving"
    ERROR = "error"
    HOMING = "homing"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class Position:
    """3D position coordinates."""
    x: float
    y: float
    z: float


@dataclass
class CommandAck:
    """Command acknowledgment."""
    id: str
    status: CommandStatus
    message: str
    timestamp: float
    stack_trace: Optional[str] = None  # For error diagnostics


@dataclass
class TelemetryData:
    """Telemetry data structure."""
    timestamp: float
    nozzle: Position
    status: SystemStatus
    error_message: Optional[str] = None


class HardwareInterface(ABC):
    """
    Abstract base class for hardware implementations.
    
    Both local and connected modes must implement this interface to ensure
    consistent behavior and API compatibility.
    
    Thread Safety:
    - Command queue operations are protected by asyncio.Lock
    - Hardware methods should be non-blocking or use run_in_executor
    - All methods return CommandAck when operations complete (not fire-and-forget)
    
    Blocking Hardware Calls:
    - pigpio, pyserial, and picamera2 operations may be blocking
    - Implementations should use loop.run_in_executor() for blocking calls
    - Document which methods are expected to block vs be awaitable
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize hardware interface with configuration."""
        self.config = config
        self.system_status = SystemStatus.IDLE
        self.emergency_stop_active = False
        self.command_queue = []
        self.current_command_id: Optional[str] = None
        self.command_history: Dict[str, CommandAck] = {}
        self._queue_lock = asyncio.Lock()
        self.logger = logging.getLogger(f"{self.__class__.__name__}")
        
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize hardware and perform startup checks.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> bool:
        """
        Shutdown hardware gracefully.
        
        Returns:
            bool: True if shutdown successful, False otherwise
        """
        pass
    
    # Nozzle control methods
    @abstractmethod
    async def move_nozzle(self, x: float, y: float, z: float, feedrate: int) -> CommandAck:
        """
        Move printer nozzle to specified position.
        
        Args:
            x: X coordinate in mm
            y: Y coordinate in mm
            z: Z coordinate in mm
            feedrate: Movement speed in mm/min
            
        Returns:
            CommandAck: Command acknowledgment
        """
        pass
    
    @abstractmethod
    async def move_nozzle_xy(self, x: float, y: float, feedrate: int) -> CommandAck:
        """
        Move printer nozzle XY only (Z unchanged).
        
        Args:
            x: X coordinate in mm
            y: Y coordinate in mm
            feedrate: Movement speed in mm/min
            
        Returns:
            CommandAck: Command acknowledgment
        """
        pass
    
    @abstractmethod
    async def move_nozzle_z(self, z: float, feedrate: int) -> CommandAck:
        """
        Move printer nozzle Z only (XY unchanged).
        
        Args:
            z: Z coordinate in mm
            feedrate: Movement speed in mm/min
            
        Returns:
            CommandAck: Command acknowledgment
        """
        pass
    
    @abstractmethod
    async def get_nozzle_position(self) -> Position:
        """
        Get current nozzle position.
        
        Returns:
            Position: Current nozzle coordinates (x, y, z)
        """
        pass
    
    @abstractmethod
    async def home_nozzle(self) -> CommandAck:
        """
        Home the nozzle to origin (0, 0, 0).
        
        Returns:
            CommandAck: Command acknowledgment
        """
        pass
    
    # Emergency stop
    @abstractmethod
    async def emergency_stop(self) -> CommandAck:
        """
        Emergency stop all movement.
        
        Returns:
            CommandAck: Command acknowledgment
        """
        pass
    
    @abstractmethod
    async def clear_emergency_stop(self) -> CommandAck:
        """
        Clear emergency stop condition.
        
        Returns:
            CommandAck: Command acknowledgment
        """
        pass
    
    # Camera methods
    @abstractmethod
    async def start_camera_stream(self) -> str:
        """
        Start camera preview stream.
        
        Returns:
            str: Stream URL for MJPEG preview
        """
        pass
    
    @abstractmethod
    async def stop_camera_stream(self) -> bool:
        """
        Stop camera preview stream.
        
        Returns:
            bool: True if stopped successfully
        """
        pass
    
    @abstractmethod
    async def capture_high_res(self) -> str:
        """
        Capture high-resolution image.
        
        Returns:
            str: Filename or URL of captured image
        """
        pass
    
    # Telemetry and status
    @abstractmethod
    async def get_telemetry(self) -> TelemetryData:
        """
        Get current system telemetry.
        
        Returns:
            TelemetryData: Current system state and positions
        """
        pass
    
    @abstractmethod
    async def is_ready(self) -> bool:
        """
        Check if hardware is ready for commands.
        
        Considers:
        - System status (not ERROR or EMERGENCY_STOP)
        - Emergency stop not active
        
        Returns:
            bool: True if ready, False if not
        """
        pass
    
    # Safety and limits
    @abstractmethod
    def check_nozzle_limits(self, x: float, y: float, z: float) -> bool:
        """
        Check if nozzle position is within safe limits.
        
        Args:
            x: X coordinate in mm
            y: Y coordinate in mm
            z: Z coordinate in mm
            
        Returns:
            bool: True if within limits, False otherwise
        """
        pass
    
    # Command queue management
    async def queue_command(self, command_type: str, **kwargs) -> str:
        """
        Queue a command for execution.
        
        Args:
            command_type: Type of command to queue
            **kwargs: Command parameters
            
        Returns:
            str: Command ID (UUID4 for uniqueness)
        """
        command_id = str(uuid.uuid4())
        command = {
            'id': command_id,
            'type': command_type,
            'params': kwargs,
            'timestamp': time.time()
        }
        
        async with self._queue_lock:
            self.command_queue.append(command)
            # Create pending ack
            self.command_history[command_id] = CommandAck(
                id=command_id,
                status=CommandStatus.PENDING,
                message="Command queued",
                timestamp=time.time()
            )
        
        return command_id
    
    async def process_command_queue(self) -> Optional[CommandAck]:
        """
        Process the next command in the queue.
        
        Performs safety checks before dispatch and updates system status.
        
        Returns:
            CommandAck: Command acknowledgment if command processed, None if queue empty
        """
        async with self._queue_lock:
            if not self.command_queue or self.current_command_id:
                return None
                
            command = self.command_queue.pop(0)
            self.current_command_id = command['id']
        
        # Update system status to MOVING
        self.system_status = SystemStatus.MOVING
        
        try:
            # Safety checks before dispatch
            if command['type'] in ['move_nozzle', 'move_nozzle_xy', 'move_nozzle_z']:
                params = command['params']
                if command['type'] == 'move_nozzle':
                    if not self.check_nozzle_limits(params['x'], params['y'], params['z']):
                        ack = CommandAck(
                            id=command['id'],
                            status=CommandStatus.ERROR,
                            message="Position outside safe limits",
                            timestamp=time.time()
                        )
                        return self._finalize_command(ack)
                elif command['type'] == 'move_nozzle_xy':
                    if not self.check_nozzle_limits(params['x'], params['y'], 0):  # Z unchanged
                        ack = CommandAck(
                            id=command['id'],
                            status=CommandStatus.ERROR,
                            message="Position outside safe limits",
                            timestamp=time.time()
                        )
                        return self._finalize_command(ack)
                elif command['type'] == 'move_nozzle_z':
                    if not self.check_nozzle_limits(0, 0, params['z']):  # XY unchanged
                        ack = CommandAck(
                            id=command['id'],
                            status=CommandStatus.ERROR,
                            message="Position outside safe limits",
                            timestamp=time.time()
                        )
                        return self._finalize_command(ack)
            
            # Check emergency stop before any operation
            if self.emergency_stop_active:
                ack = CommandAck(
                    id=command['id'],
                    status=CommandStatus.ERROR,
                    message="Emergency stop active",
                    timestamp=time.time()
                )
                return self._finalize_command(ack)
            
            # Route command to appropriate method
            if command['type'] == 'move_nozzle':
                ack = await self.move_nozzle(**command['params'])
            elif command['type'] == 'move_nozzle_xy':
                ack = await self.move_nozzle_xy(**command['params'])
            elif command['type'] == 'move_nozzle_z':
                ack = await self.move_nozzle_z(**command['params'])
            elif command['type'] == 'emergency_stop':
                ack = await self.emergency_stop()
            else:
                ack = CommandAck(
                    id=command['id'],
                    status=CommandStatus.ERROR,
                    message=f"Unknown command type: {command['type']}",
                    timestamp=time.time()
                )
        except Exception as e:
            # Log exception for diagnostics
            self.logger.error(f"Command {command['id']} failed: {e}", exc_info=True)
            ack = CommandAck(
                id=command['id'],
                status=CommandStatus.ERROR,
                message=str(e),
                timestamp=time.time(),
                stack_trace=traceback.format_exc()
            )
        finally:
            # Update system status back to IDLE
            if not self.emergency_stop_active:
                self.system_status = SystemStatus.IDLE
            self.current_command_id = None
            
        return self._finalize_command(ack)
    
    def _finalize_command(self, ack: CommandAck) -> CommandAck:
        """Store command result in history and return ack."""
        self.command_history[ack.id] = ack
        return ack
    
    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current command queue status.
        
        Returns:
            Dict: Queue status information
        """
        return {
            'queue_length': len(self.command_queue),
            'current_command_id': self.current_command_id,
            'system_status': self.system_status.value,
            'emergency_stop': self.emergency_stop_active,
            'command_history_size': len(self.command_history)
        }
    
    def get_command_status(self, command_id: str) -> Optional[CommandAck]:
        """
        Get status of a specific command.
        
        Args:
            command_id: Command ID to look up
            
        Returns:
            CommandAck: Command status if found, None otherwise
        """
        return self.command_history.get(command_id)
    
    def get_command_history(self, limit: int = 100) -> Dict[str, CommandAck]:
        """
        Get recent command history.
        
        Args:
            limit: Maximum number of commands to return
            
        Returns:
            Dict: Recent command history (command_id -> CommandAck)
        """
        # Return most recent commands
        sorted_commands = sorted(
            self.command_history.items(),
            key=lambda x: x[1].timestamp,
            reverse=True
        )
        return dict(sorted_commands[:limit])
