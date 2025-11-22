"""
Hardware factory for creating appropriate hardware implementations.

Creates the correct hardware interface based on the specified mode.
"""

from typing import Dict, Any
from .abstract_hardware import HardwareInterface
from .local_hardware import LocalHardware
from .connected_hardware import ConnectedHardware


def create_hardware(mode: str, config: Dict[str, Any]) -> HardwareInterface:
    """
    Create hardware interface based on mode.
    
    Args:
        mode: Hardware mode ('local' or 'connected')
        config: Configuration dictionary
        
    Returns:
        HardwareInterface: Appropriate hardware implementation
        
    Raises:
        ValueError: If mode is not supported
    """
    if mode == "local":
        return LocalHardware(config)
    elif mode == "connected":
        return ConnectedHardware(config)
    else:
        raise ValueError(f"Unknown hardware mode: {mode}. Must be 'local' or 'connected'")
