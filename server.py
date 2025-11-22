"""
Main server for printer interface system.

Supports both local and connected modes with hardware abstraction.
"""

import sys
import os
import asyncio
import argparse
import yaml
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from hw.hardware_factory import create_hardware
from hw.abstract_hardware import CommandStatus, SystemStatus


def load_config(config_file: str) -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to load config {config_file}: {e}")
        sys.exit(1)


def create_app(mode: str, config: dict):
    """Create Flask application with hardware interface."""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'printer_interface_secret_key'
    
    # Create hardware interface
    hardware = create_hardware(mode, config)
    
    # Initialize SocketIO
    socketio = SocketIO(app, cors_allowed_origins="*")
    
    # Global variables for hardware and telemetry
    app.hardware = hardware
    app.socketio = socketio
    app.mode = mode
    
    @app.route('/')
    def index():
        """Serve main UI."""
        return render_template('index.html', mode=mode)
    
    @app.route('/stream')
    def stream():
        """Camera stream endpoint."""
        # This would be implemented with picamera2 for MJPEG streaming
        return "Camera stream not implemented yet", 501
    
    @app.route('/capture', methods=['POST'])
    def capture():
        """Capture high-resolution image."""
        try:
            filename = asyncio.run(hardware.capture_high_res())
            return jsonify({'filename': filename, 'success': True})
        except Exception as e:
            return jsonify({'error': str(e), 'success': False}), 500
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        print(f"Client connected in {mode} mode")
        emit('status', {'mode': mode, 'connected': True})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        print("Client disconnected")
    
    @socketio.on('cmd.zoom')
    def handle_zoom_command(data):
        """Handle zoom commands."""
        action = data.get('action')
        value = data.get('value', 100)
        
        async def execute_zoom():
            if action == 'in':
                ack = await hardware.zoom_in(value)
            elif action == 'out':
                ack = await hardware.zoom_out(value)
            elif action == 'home':
                ack = await hardware.home_zoom()
            else:
                ack = hardware.CommandAck(
                    id=f"zoom_{int(time.time() * 1000)}",
                    status=CommandStatus.ERROR,
                    message=f"Unknown zoom action: {action}",
                    timestamp=time.time()
                )
            
            emit('telemetry.command_ack', {
                'id': ack.id,
                'status': ack.status.value,
                'message': ack.message,
                'timestamp': ack.timestamp
            })
        
        asyncio.create_task(execute_zoom())
    
    @socketio.on('cmd.move_nozzle')
    def handle_move_nozzle_command(data):
        """Handle nozzle movement commands."""
        x = data.get('x', 0)
        y = data.get('y', 0)
        z = data.get('z', 0)
        feedrate = data.get('feedrate', 1500)
        
        async def execute_move():
            ack = await hardware.move_nozzle(x, y, z, feedrate)
            emit('telemetry.command_ack', {
                'id': ack.id,
                'status': ack.status.value,
                'message': ack.message,
                'timestamp': ack.timestamp
            })
        
        asyncio.create_task(execute_move())
    
    @socketio.on('cmd.move_nozzle_xy')
    def handle_move_nozzle_xy_command(data):
        """Handle nozzle XY movement commands."""
        x = data.get('x', 0)
        y = data.get('y', 0)
        feedrate = data.get('feedrate', 1500)
        
        async def execute_move():
            ack = await hardware.move_nozzle_xy(x, y, feedrate)
            emit('telemetry.command_ack', {
                'id': ack.id,
                'status': ack.status.value,
                'message': ack.message,
                'timestamp': ack.timestamp
            })
        
        asyncio.create_task(execute_move())
    
    @socketio.on('cmd.move_nozzle_z')
    def handle_move_nozzle_z_command(data):
        """Handle nozzle Z movement commands."""
        z = data.get('z', 0)
        feedrate = data.get('feedrate', 1500)
        
        async def execute_move():
            ack = await hardware.move_nozzle_z(z, feedrate)
            emit('telemetry.command_ack', {
                'id': ack.id,
                'status': ack.status.value,
                'message': ack.message,
                'timestamp': ack.timestamp
            })
        
        asyncio.create_task(execute_move())
    
    @socketio.on('cmd.emergency_stop')
    def handle_emergency_stop():
        """Handle emergency stop command."""
        async def execute_emergency_stop():
            ack = await hardware.emergency_stop()
            emit('telemetry.command_ack', {
                'id': ack.id,
                'status': ack.status.value,
                'message': ack.message,
                'timestamp': ack.timestamp
            })
        
        asyncio.create_task(execute_emergency_stop())
    
    # Telemetry task
    async def telemetry_task():
        """Periodic telemetry emission."""
        while True:
            try:
                telemetry = await hardware.get_telemetry()
                socketio.emit('telemetry.position', {
                    'timestamp': telemetry.timestamp,
                    'nozzle': {
                        'x': telemetry.nozzle.x,
                        'y': telemetry.nozzle.y,
                        'z': telemetry.nozzle.z
                    },
                    'zoom': {
                        's_prime_mm': telemetry.zoom.s_prime_mm,
                        'magnification': telemetry.zoom.magnification,
                        'pct': telemetry.zoom.percentage
                    },
                    'status': telemetry.status.value
                })
            except Exception as e:
                print(f"Telemetry error: {e}")
            
            await asyncio.sleep(0.5)  # 2 Hz telemetry
    
    # Start telemetry task
    asyncio.create_task(telemetry_task())
    
    return app


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Printer Interface Server')
    parser.add_argument('--mode', choices=['local', 'connected'], 
                       default=os.getenv('PRINTER_MODE', 'local'),
                       help='Hardware mode (local or connected)')
    parser.add_argument('--config', 
                       default=f'config_{os.getenv("PRINTER_MODE", "local")}.yml',
                       help='Configuration file path')
    parser.add_argument('--port', type=int, default=5000,
                       help='Port to run server on')
    parser.add_argument('--host', default='0.0.0.0',
                       help='Host to bind server to')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Determine port based on mode if not specified
    if args.port == 5000:  # Default port
        args.port = 5000 if args.mode == 'local' else 5001
    
    print(f"Starting {args.mode} mode server on {args.host}:{args.port}")
    
    # Create and run app
    app = create_app(args.mode, config)
    
    # Initialize hardware
    async def init_hardware():
        success = await app.hardware.initialize()
        if not success:
            print(f"ERROR: Failed to initialize {args.mode} hardware")
            sys.exit(1)
        print(f"{args.mode.capitalize()} hardware initialized successfully")
    
    asyncio.run(init_hardware())
    
    # Run server
    app.socketio.run(app, host=args.host, port=args.port, debug=True)


if __name__ == '__main__':
    main()
