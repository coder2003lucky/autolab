"""
Hardware factory for creating appropriate hardware implementations.

Creates the correct hardware interface based on the specified mode.
"""

from typing import Dict, Any
from .abstract_hardware import HardwareInterface
from .test_hardware import TestHardware
from .connected_hardware import ConnectedHardware


def create_hardware(mode: str, config: Dict[str, Any]) -> HardwareInterface:
    """
    Create hardware interface based on mode.
    
    Args:
        mode: Hardware mode ('test' or 'connected')
            - 'test': Simulates hardware behavior without sending Arduino commands
            - 'connected': Sends actual Arduino commands to real hardware
        config: Configuration dictionary
        
    Returns:
        HardwareInterface: Appropriate hardware implementation
        
    Raises:
        ValueError: If mode is not supported
    """
    if mode == "test":
        return TestHardware(config)
    elif mode == "connected":
        return ConnectedHardware(config)
    else:
        raise ValueError(f"Unknown hardware mode: {mode}. Must be 'test' or 'connected'")
