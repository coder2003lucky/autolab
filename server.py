"""
Main server for printer interface system with integrated camera streaming.

Supports both test and connected modes with hardware abstraction.
Test mode: Simulates hardware behavior without sending Arduino commands
Connected mode: Sends actual Arduino commands to real hardware
"""

import sys
import os
import asyncio
import argparse
import yaml
import time
import io
import threading
from flask import Flask, render_template, jsonify, Response, request
from flask_socketio import SocketIO, emit
from hw.hardware_factory import create_hardware
from hw.abstract_hardware import CommandStatus, SystemStatus


def load_config(config_file: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)


class CameraStream:
    """Camera streaming handler."""
    
    def __init__(self, config: dict, mode: str):
        self.config = config
        self.mode = mode
        self.picam2 = None
        self.camera_lock = threading.Lock()
    
    def get_camera(self):
        """Initialize and return camera instance."""
        if self.picam2 is None:
            with self.camera_lock:
                if self.picam2 is None:
                    print("Initializing camera (this may take a few seconds)...", flush=True)
                    try:
                        from picamera2 import Picamera2
                        # Initialize camera - try to detect automatically, but allow explicit camera index
                        # For HQ Camera (IMX477), it should auto-detect, but we can specify camera index if needed
                        try:
                            # Try with explicit camera index 0 (default camera)
                            self.picam2 = Picamera2(camera_num=0)
                            print("  Camera object created (camera 0), configuring...", flush=True)
                        except Exception as e:
                            print(f"  Warning: Failed to initialize camera 0: {e}", flush=True)
                            # Fallback: try without explicit index
                            self.picam2 = Picamera2()
                            print("  Camera object created (auto-detect), configuring...", flush=True)
                        
                        # Print camera info for debugging
                        try:
                            camera_info = self.picam2.camera_properties
                            print(f"  Camera model: {camera_info.get('Model', 'Unknown')}", flush=True)
                            sensor_model = camera_info.get('Model', 'Unknown')
                            if 'IMX477' in str(sensor_model) or '477' in str(sensor_model):
                                print("  ✓ Detected IMX477 sensor (HQ Camera)", flush=True)
                            else:
                                print(f"  ⚠ Camera sensor: {sensor_model} (expected IMX477 for HQ Camera)", flush=True)
                        except Exception as e:
                            print(f"  Note: Could not get camera info: {e}", flush=True)
                        
                        # Get stream settings from config
                        preview_width = self.config.get('stream', {}).get('preview_width', 1280)
                        preview_height = self.config.get('stream', {}).get('preview_height', 720)
                        preview_fps = self.config.get('stream', {}).get('preview_fps', 30)
                        
                        # Create video configuration - keep basic controls only
                        # Quality controls will be applied after camera starts
                        # For HQ Camera (IMX477) with manual focus C-mount lens
                        try:
                            video_config = self.picam2.create_video_configuration(
                                main={"size": (preview_width, preview_height)},
                                controls={"FrameRate": preview_fps}
                            )
                            print(f"  Video config created: {preview_width}x{preview_height} @ {preview_fps}fps", flush=True)
                        except Exception as e:
                            print(f"  Warning: Failed to create video config with size {preview_width}x{preview_height}: {e}", flush=True)
                            # Try with a standard resolution that should work
                            print("  Trying with standard 1280x720 resolution...", flush=True)
                            preview_width, preview_height = 1280, 720
                            preview_fps = 15
                            video_config = self.picam2.create_video_configuration(
                                main={"size": (preview_width, preview_height)},
                                controls={"FrameRate": preview_fps}
                            )
                        
                        self.picam2.configure(video_config)
                        print("  Camera configured, starting...", flush=True)
                        self.picam2.start()
                        print("  Camera started, waiting for stabilization...", flush=True)
                        
                        # Allow camera to stabilize
                        time.sleep(1)
                        
                        # Apply image quality controls after camera starts
                        try:
                            available_controls = self.picam2.camera_controls
                            print(f"  Available camera controls: {list(available_controls.keys())[:10]}...", flush=True)
                            
                            # Try to set image quality controls
                            quality_controls = {}
                            
                            # Sharpness control (if available)
                            if 'Sharpness' in available_controls:
                                sharpness = self.config.get('camera', {}).get('sharpness', 2.0)
                                quality_controls['Sharpness'] = float(sharpness)
                                print(f"  Setting Sharpness to {sharpness}", flush=True)
                            
                            # Noise reduction
                            if 'NoiseReductionMode' in available_controls:
                                quality_controls['NoiseReductionMode'] = 2  # Fast mode for streaming
                                print("  Setting NoiseReductionMode to 2 (fast)", flush=True)
                            
                            # JPEG quality control (for video streaming)
                            jpeg_quality = self.config.get('camera', {}).get('jpeg_quality', 85)
                            if 'Quality' in available_controls:
                                quality_controls['Quality'] = int(jpeg_quality)
                                print(f"  Setting JPEG Quality to {jpeg_quality}", flush=True)
                            
                            # Note: LensPosition control is for motorized focus lenses only
                            # The Arducam LN046 is a physical manual focus lens - adjust the focus ring on the lens itself
                            # This control may not work for simple manual focus lenses
                            focus_distance = self.config.get('camera', {}).get('focus_distance', None)
                            if focus_distance is not None and 'LensPosition' in available_controls:
                                try:
                                    quality_controls['LensPosition'] = float(focus_distance)
                                    print(f"  Attempting to set LensPosition (focus) to {focus_distance}", flush=True)
                                    print("  Note: This may not work for physical manual focus lenses like LN046", flush=True)
                                except Exception as e:
                                    print(f"  LensPosition control not supported: {e}", flush=True)
                            
                            # Try autofocus if available (for autofocus lenses)
                            if 'AfMode' in available_controls:
                                print("  Autofocus available - enabling...", flush=True)
                                quality_controls.update({
                                    "AfMode": 1,  # Auto focus mode (1 = continuous)
                                    "AfSpeed": 1,  # Fast autofocus
                                })
                                self.picam2.set_controls(quality_controls)
                                time.sleep(0.5)
                                # Trigger autofocus
                                self.picam2.set_controls({"AfTrigger": 1})
                                print("  Autofocus enabled and triggered", flush=True)
                                time.sleep(1.5)  # Wait for autofocus to complete
                            elif quality_controls:
                                # Apply manual focus and quality settings
                                self.picam2.set_controls(quality_controls)
                                print("  Manual focus and quality settings applied", flush=True)
                            else:
                                print("  Note: Autofocus not available - using manual focus", flush=True)
                                print("  Adjust focus manually using the lens focus ring", flush=True)
                        except Exception as e:
                            print(f"  Note: Could not set all camera controls: {e}", flush=True)
                            print("  This is normal for some manual focus lenses", flush=True)
                        
                        print("Camera initialization complete.", flush=True)
                    except Exception as e:
                        print(f"ERROR: Camera initialization failed: {e}", flush=True)
                        import traceback
                        traceback.print_exc()
                        raise
        return self.picam2
    
    def generate_frames(self):
        """Generator function that yields MJPEG frames."""
        try:
            camera = self.get_camera()
        except Exception as e:
            print(f"Failed to get camera: {e}", flush=True)
            # Yield an error frame instead of crashing
            error_frame = b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + b'\xff\xd8\xff\xe0' + b'\r\n'
            yield error_frame
            return
        
        frame_count = 0
        print("Starting frame generation loop...", flush=True)
        while True:
            try:
                # Use capture_file which handles JPEG encoding efficiently
                # This is the recommended method for MJPEG streaming
                # JPEG quality is set via camera controls (see get_camera method)
                stream = io.BytesIO()
                camera.capture_file(stream, format='jpeg')
                stream.seek(0)
                frame_bytes = stream.getvalue()
                
                if len(frame_bytes) == 0:
                    print("Warning: Empty frame captured", flush=True)
                    time.sleep(0.1)
                    continue
                
                frame_count += 1
                if frame_count == 1:
                    print(f"✓ First frame captured: {len(frame_bytes)} bytes", flush=True)
                elif frame_count % 30 == 0:
                    print(f"Streaming: {frame_count} frames captured", flush=True)
                
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                # Adjust sleep based on configured FPS
                fps = self.config.get('stream', {}).get('preview_fps', 30)
                time.sleep(1.0 / fps)
            except Exception as e:
                print(f"Frame capture error: {e}", flush=True)
                import traceback
                traceback.print_exc()
                time.sleep(1)  # Wait longer on error before retrying
    
    def cleanup(self):
        """Cleanup camera resources."""
        if self.picam2:
            self.picam2.stop()
            self.picam2.close()


def create_app(mode: str, config: dict):
    """Create Flask application with hardware interface and camera streaming."""
    app = Flask(__name__, 
                template_folder='ui/templates',
                static_folder='ui/static',
                static_url_path='/static')
    app.config['SECRET_KEY'] = 'printer_interface_secret_key'
    
    print(f"  Creating hardware interface...", flush=True)
    hardware = create_hardware(mode, config)
    print(f"  Creating camera stream...", flush=True)
    camera_stream = CameraStream(config, mode)
    print(f"  Creating SocketIO...", flush=True)
    # Use threading mode for better compatibility
    socketio = SocketIO(
        app, 
        cors_allowed_origins="*",
        async_mode='threading',  # Use threading mode for better compatibility
        logger=False,  # Disable verbose logging to reduce noise
        engineio_logger=False  # Disable engineio logging
    )
    
    app.hardware = hardware
    app.socketio = socketio
    app.mode = mode
    app.camera_stream = camera_stream
    
    @app.route('/test')
    def test():
        return "Server is working!"
    
    @app.route('/')
    def index():
        print(f"Serving index page for {mode} mode")
        return render_template('index.html', mode=mode)
    
    @app.route('/stream')
    def stream():
        # Don't print here - it's called frequently and causes spam
        try:
            # Generate frames - camera initialization happens lazily in generate_frames
            return Response(
                camera_stream.generate_frames(),
                mimetype='multipart/x-mixed-replace; boundary=frame',
                headers={
                    'Cache-Control': 'no-cache, no-store, must-revalidate',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )
        except Exception as e:
            print(f"Stream error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return f"Stream error: {e}", 500
    
    @app.route('/capture', methods=['POST'])
    def capture():
        filename = asyncio.run(hardware.capture_high_res())
        return jsonify({'filename': filename, 'success': True})
    
    @app.route('/config')
    def get_config():
        """Return printer safe limits and settings for 3D visualization."""
        safe_limits = config.get('printer', {}).get('safe_limits', {})
        return jsonify({
            'x_min': safe_limits.get('x_min', 0),
            'x_max': safe_limits.get('x_max', 220),
            'y_min': safe_limits.get('y_min', 0),
            'y_max': safe_limits.get('y_max', 220),
            'z_min': safe_limits.get('z_min', 0),
            'z_max': safe_limits.get('z_max', 250),
            'move_feedrate_default': config.get('printer', {}).get('move_feedrate_default', 1500)
        })
    
    @socketio.on('connect')
    def handle_connect():
        try:
            # Safely get client address
            try:
                client_addr = request.remote_addr if hasattr(request, 'remote_addr') else 'unknown'
            except:
                client_addr = 'unknown'
            print(f"Client connecting from {client_addr}...", flush=True)
            # Emit status after connection is established
            try:
                emit('status', {'mode': mode, 'connected': True})
            except Exception as emit_error:
                print(f"Warning: Failed to emit status: {emit_error}", flush=True)
            
            # Start telemetry when first client connects
            if not hasattr(app, '_telemetry_started'):
                app._telemetry_started = True
                def telemetry_task():
                    time.sleep(0.5)  # Small delay
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        while True:
                            try:
                                telemetry = loop.run_until_complete(hardware.get_telemetry())
                                socketio.emit('telemetry.position', {
                                    'timestamp': telemetry.timestamp,
                                    'nozzle': {
                                        'x': telemetry.nozzle.x,
                                        'y': telemetry.nozzle.y,
                                        'z': telemetry.nozzle.z
                                    },
                                    'status': telemetry.status.value
                                })
                            except Exception as e:
                                print(f"Telemetry error: {e}", flush=True)
                            time.sleep(0.5)
                    except KeyboardInterrupt:
                        pass
                    except Exception as e:
                        print(f"Telemetry task error: {e}", flush=True)
                    finally:
                        try:
                            loop.close()
                        except:
                            pass
                
                try:
                    socketio.start_background_task(telemetry_task)
                    print("Telemetry task started", flush=True)
                except Exception as e:
                    print(f"Failed to start telemetry task: {e}", flush=True)
            
            print(f"Client connected successfully from {client_addr}", flush=True)
        except Exception as e:
            print(f"Error in handle_connect: {e}", flush=True)
            import traceback
            traceback.print_exc()
            # Don't re-raise - let the connection proceed even if there's an error
    
    @socketio.on('disconnect')
    def handle_disconnect():
        try:
            client_addr = request.remote_addr if hasattr(request, 'remote_addr') else 'unknown'
        except:
            client_addr = 'unknown'
        print(f"Client disconnected from {client_addr}", flush=True)
    
    @socketio.on('cmd.move_nozzle')
    def handle_move_nozzle_command(data):
        def execute_move():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                default_feedrate = config.get('printer', {}).get('move_feedrate_default', 1500)
                ack = loop.run_until_complete(hardware.move_nozzle(
                    data.get('x', 0),
                    data.get('y', 0),
                    data.get('z', 0),
                    data.get('feedrate', default_feedrate)
                ))
                emit('telemetry.command_ack', {
                    'id': ack.id,
                    'status': ack.status.value,
                    'message': ack.message,
                    'timestamp': ack.timestamp
                })
            finally:
                loop.close()
        socketio.start_background_task(execute_move)
    
    @socketio.on('cmd.move_nozzle_xy')
    def handle_move_nozzle_xy_command(data):
        def execute_move():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                default_feedrate = config.get('printer', {}).get('move_feedrate_default', 1500)
                ack = loop.run_until_complete(hardware.move_nozzle_xy(
                    data.get('x', 0),
                    data.get('y', 0),
                    data.get('feedrate', default_feedrate)
                ))
                emit('telemetry.command_ack', {
                    'id': ack.id,
                    'status': ack.status.value,
                    'message': ack.message,
                    'timestamp': ack.timestamp
                })
            finally:
                loop.close()
        socketio.start_background_task(execute_move)
    
    @socketio.on('cmd.move_nozzle_z')
    def handle_move_nozzle_z_command(data):
        def execute_move():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                default_feedrate = config.get('printer', {}).get('move_feedrate_default', 1500)
                ack = loop.run_until_complete(hardware.move_nozzle_z(
                    data.get('z', 0),
                    data.get('feedrate', default_feedrate)
                ))
                emit('telemetry.command_ack', {
                    'id': ack.id,
                    'status': ack.status.value,
                    'message': ack.message,
                    'timestamp': ack.timestamp
                })
            finally:
                loop.close()
        socketio.start_background_task(execute_move)
    
    @socketio.on('cmd.home_nozzle')
    def handle_home_nozzle():
        def execute_home():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                ack = loop.run_until_complete(hardware.home_nozzle())
                emit('telemetry.command_ack', {
                    'id': ack.id,
                    'status': ack.status.value,
                    'message': ack.message,
                    'timestamp': ack.timestamp
                })
            finally:
                loop.close()
        socketio.start_background_task(execute_home)
    
    @socketio.on('cmd.emergency_stop')
    def handle_emergency_stop():
        def execute_emergency_stop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                ack = loop.run_until_complete(hardware.emergency_stop())
                emit('telemetry.command_ack', {
                    'id': ack.id,
                    'status': ack.status.value,
                    'message': ack.message,
                    'timestamp': ack.timestamp
                })
            finally:
                loop.close()
        socketio.start_background_task(execute_emergency_stop)
    
    return app


def main():
    parser = argparse.ArgumentParser(description='Printer Interface Server')
    parser.add_argument('--mode', choices=['test', 'connected'], 
                       default=os.getenv('MODE', 'test'),
                       help='Hardware mode: test (simulation) or connected (real hardware)')
    parser.add_argument('--config', default=None,
                       help='Configuration file path (default: config_{mode}.yml)')
    parser.add_argument('--port', type=int, default=5000, help='Port to run server on')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind server to')
    
    args = parser.parse_args()
    
    config = load_config(args.config or f'config_{args.mode}.yml')
    
    print(f"Starting {args.mode} mode server on {args.host}:{args.port}", flush=True)
    
    print("Creating Flask app...", flush=True)
    app = create_app(args.mode, config)
    print("Flask app created.", flush=True)
    
    # Initialize hardware - fail fast on error
    async def init_hardware():
        print(f"Initializing {args.mode} hardware...", flush=True)
        try:
            if not await app.hardware.initialize():
                print(f"ERROR: Failed to initialize {args.mode} hardware", flush=True)
                sys.exit(1)
            print(f"{args.mode.capitalize()} hardware initialized successfully", flush=True)
        except Exception as e:
            print(f"ERROR: Exception during hardware initialization: {e}", flush=True)
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    print("Running hardware initialization...", flush=True)
    asyncio.run(init_hardware())
    print("Hardware initialization complete.", flush=True)
    
    print("Starting server...")
    print("Press Ctrl+C to stop")
    
    import atexit
    def cleanup():
        print("\nCleaning up...")
        app.camera_stream.cleanup()
        asyncio.run(app.hardware.shutdown())
    atexit.register(cleanup)
    
    print(f"Server ready at http://{args.host}:{args.port}")
    app.socketio.run(app, host=args.host, port=args.port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    main()
