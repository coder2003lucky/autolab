/**
 * Printer Interface Frontend JavaScript
 * Handles SocketIO communication and UI updates
 */

class PrinterInterface {
    constructor() {
        this.socket = null;
        this.mode = this.detectMode();
        this.connected = false;
        this.systemStatus = 'idle';
        this.lastCommand = null;
        this.currentPosition = { x: 0, y: 0, z: 0 };
        this.config = null;
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.nozzleMarker = null;
        this.workspaceBox = null;
        this.moving = false; // Track if a movement is in progress
        this.animationFrameId = null; // Track animation frame for cleanup
        this.needsRender = false; // Flag to indicate if render is needed
        this._waitingForThree = false; // Prevent duplicate waitForThreeAndInit calls
        this._visualizationInitialized = false; // Prevent duplicate initialization
        
        // Load config and initialize
        console.log('Starting config load...');
        this.loadConfig().then(() => {
            console.log('Config loaded successfully:', this.config);
            this.initializeSocket();
            // Wait for DOM to be ready before binding events
            const initUI = () => {
                console.log('Initializing UI components...');
                this.bindEvents();
                this.updateUI();
                // Ensure THREE.js is loaded before initializing visualization
                console.log('Calling waitForThreeAndInit...');
                this.waitForThreeAndInit();
            };
            
            console.log('Document ready state:', document.readyState);
            if (document.readyState === 'loading') {
                console.log('DOM still loading, waiting for DOMContentLoaded...');
                document.addEventListener('DOMContentLoaded', initUI);
            } else {
                // DOM already ready
                console.log('DOM already ready, initializing UI now...');
                initUI();
            }
        }).catch((error) => {
            console.error('Failed to load config:', error);
            // Still try to initialize with defaults
            this.initializeSocket();
            const initUI = () => {
                console.log('Initializing UI with default config...');
                this.bindEvents();
                this.updateUI();
                console.log('Calling waitForThreeAndInit (with defaults)...');
                this.waitForThreeAndInit();
            };
            
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', initUI);
            } else {
                initUI();
            }
        });
    }
    
    async loadConfig() {
        try {
            console.log('Fetching config from /config endpoint...');
            // Use cache to avoid re-fetching on every page load, but add timeout
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout (increased)
            
            const response = await fetch('/config', { 
                cache: 'default',
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`Config endpoint returned ${response.status}: ${response.statusText}`);
            }
            
            this.config = await response.json();
            console.log('Config fetched successfully');
        } catch (error) {
            // Don't treat AbortError as a critical failure if it's just a timeout
            if (error.name === 'AbortError') {
                console.warn('Config fetch timed out, using defaults');
            } else {
                console.error('Failed to load config:', error);
            }
            console.log('Using default config values');
            // Default values
            this.config = {
                x_min: 0, x_max: 220,
                y_min: 0, y_max: 220,
                z_min: 0, z_max: 250,
                move_feedrate_default: 1500
            };
        }
    }
    
    detectMode() {
        // Check for mode in page title or data attribute
        const modeElement = document.querySelector('.mode-badge');
        if (modeElement) {
            const modeText = modeElement.textContent.toLowerCase();
            if (modeText.includes('test')) return 'test';
            if (modeText.includes('connected')) return 'connected';
        }
        
        // Check URL port
        if (window.location.port === '5000') return 'test';
        if (window.location.port === '5001') return 'connected';
        
        return 'test'; // Default
    }
    
    initializeSocket() {
        // Use current host and port
        console.log('Initializing socket connection...');
        console.log('Current URL:', window.location.href);
        console.log('SocketIO URL will be:', window.location.origin);
        
        // Try with explicit transport options and longer timeout
        this.socket = io(window.location.origin, {
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            reconnectionAttempts: 10,
            timeout: 20000,  // 20 second timeout
            transports: ['websocket', 'polling'],  // Try websocket first, fallback to polling
            upgrade: true,
            rememberUpgrade: true
        });
        
        this.socket.on('connect', () => {
            console.log('✅ Connected to server via SocketIO');
            this.connected = true;
            this.updateConnectionStatus();
        });
        
        this.socket.on('connect_error', (error) => {
            console.error('❌ Socket connection error:', error);
            this.connected = false;
            this.updateConnectionStatus();
        });
        
        this.socket.on('disconnect', (reason) => {
            console.log('⚠️ Disconnected from server. Reason:', reason);
            this.connected = false;
            this.updateConnectionStatus();
        });
        
        this.socket.on('reconnect', (attemptNumber) => {
            console.log('✅ Reconnected to server after', attemptNumber, 'attempts');
            this.connected = true;
            this.updateConnectionStatus();
        });
        
        this.socket.on('reconnect_error', (error) => {
            console.error('❌ Reconnection error:', error);
        });
        
        this.socket.on('reconnect_failed', () => {
            console.error('❌ Failed to reconnect after all attempts');
            alert('Failed to connect to server. Please refresh the page.');
        });
        
        this.socket.on('status', (data) => {
            console.log('Status update:', data);
            this.mode = data.mode;
        });
        
        this.socket.on('telemetry.position', (data) => {
            this.updateTelemetry(data);
        });
        
        this.socket.on('telemetry.command_ack', (data) => {
            this.handleCommandAck(data);
        });
        
        // Check connection status after a short delay
        setTimeout(() => {
            if (!this.connected) {
                console.warn('⚠️ Socket not connected after initialization. Current state:', this.socket.connected);
            }
        }, 2000);
    }
    
    bindEvents() {
        // Helper function to safely bind event
        const safeBind = (id, event, handler) => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener(event, handler);
            } else {
                console.warn(`Element with id '${id}' not found, cannot bind event`);
            }
        };
        
        // Homing button
        safeBind('home-nozzle-btn', 'click', () => {
            this.homeNozzle();
        });
        
        // Incremental movement buttons (±1mm)
        safeBind('x-plus-btn', 'click', () => {
            this.moveIncremental('x', 1.0);
        });
        safeBind('x-minus-btn', 'click', () => {
            this.moveIncremental('x', -1.0);
        });
        // Incremental movement buttons (±1mm)
        safeBind('y-plus-btn', 'click', () => {
            console.log('Y+ button clicked');
            this.moveIncremental('y', 1.0);
        });
        safeBind('y-minus-btn', 'click', () => {
            console.log('Y- button clicked');
            this.moveIncremental('y', -1.0);
        });
        safeBind('z-plus-btn', 'click', () => {
            console.log('Z+ button clicked');
            this.moveIncremental('z', 1.0);
        });
        safeBind('z-minus-btn', 'click', () => {
            console.log('Z- button clicked');
            this.moveIncremental('z', -1.0);
        });
        
        // Nozzle movement controls - individual axis buttons
        safeBind('move-x-btn', 'click', () => {
            this.moveNozzleX();
        });
        
        safeBind('move-y-btn', 'click', () => {
            console.log('Move Y button clicked');
            this.moveNozzleY();
        });
        
        safeBind('move-z-btn', 'click', () => {
            console.log('Move Z button clicked');
            this.moveNozzleZ();
        });
        
        // Emergency stop
        safeBind('emergency-stop-btn', 'click', () => {
            this.emergencyStop();
        });
        
        // Camera capture
        safeBind('capture-btn', 'click', () => {
            this.captureImage();
        });
        
        // Zoom controls for 3D visualization
        safeBind('zoom-in-btn', 'click', () => {
            if (this.controls) {
                // Zoom in by reducing distance to target
                const currentDistance = this.camera.position.distanceTo(this.controls.target);
                const newDistance = Math.max(currentDistance * 0.8, this.controls.minDistance);
                const direction = new THREE.Vector3().subVectors(this.camera.position, this.controls.target).normalize();
                this.camera.position.copy(this.controls.target).add(direction.multiplyScalar(newDistance));
                this.controls.update();
                this.requestRender();
            }
        });
        
        safeBind('zoom-out-btn', 'click', () => {
            if (this.controls) {
                // Zoom out by increasing distance to target
                const currentDistance = this.camera.position.distanceTo(this.controls.target);
                const newDistance = Math.min(currentDistance * 1.2, this.controls.maxDistance);
                const direction = new THREE.Vector3().subVectors(this.camera.position, this.controls.target).normalize();
                this.camera.position.copy(this.controls.target).add(direction.multiplyScalar(newDistance));
                this.controls.update();
                this.requestRender();
            }
        });
        
        // Enter key support for inputs
        document.querySelectorAll('input[type="number"]').forEach(input => {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.handleInputEnter(e.target);
                }
            });
        });
    }
    
    handleInputEnter(input) {
        // Find the associated button and click it
        const axisControl = input.closest('.axis-control');
        if (axisControl) {
            const button = axisControl.querySelector('button');
            if (button) {
                button.click();
            }
        } else {
            // Fallback for old control-row structure
            const controlRow = input.closest('.control-row');
            const button = controlRow?.querySelector('button');
            if (button) {
                button.click();
            }
        }
    }
    
    moveNozzleX() {
        const xInput = document.getElementById('nozzle-x-input');
        const x = parseFloat(xInput.value);
        if (isNaN(x)) {
            alert('Please enter a valid X position');
            return;
        }
        // Keep current Y and Z positions
        const feedrate = this.config.move_feedrate_default || 1500;
        this.sendCommand('cmd.move_nozzle', { 
            x, 
            y: this.currentPosition.y, 
            z: this.currentPosition.z, 
            feedrate 
        });
        // Clear input and update placeholder after move
        xInput.value = '';
        xInput.placeholder = `Current: ${x.toFixed(1)} mm`;
    }
    
    moveNozzleY() {
        const yInput = document.getElementById('nozzle-y-input');
        const y = parseFloat(yInput.value);
        if (isNaN(y)) {
            alert('Please enter a valid Y position');
            return;
        }
        console.log('Move Y button clicked - moving to Y:', y, 'current position:', this.currentPosition);
        // Keep current X and Z positions
        const feedrate = this.config.move_feedrate_default || 1500;
        this.sendCommand('cmd.move_nozzle', { 
            x: this.currentPosition.x, 
            y: y,
            z: this.currentPosition.z, 
            feedrate 
        });
        // Clear input and update placeholder after move
        yInput.value = '';
        yInput.placeholder = `Current: ${y.toFixed(1)} mm`;
    }
    
    moveNozzleZ() {
        const zInput = document.getElementById('nozzle-z-input');
        const z = parseFloat(zInput.value);
        if (isNaN(z)) {
            alert('Please enter a valid Z position');
            return;
        }
        console.log('Move Z button clicked - moving to Z:', z, 'current position:', this.currentPosition);
        // Keep current X and Y positions
        const feedrate = this.config.move_feedrate_default || 1500;
        this.sendCommand('cmd.move_nozzle', { 
            x: this.currentPosition.x, 
            y: this.currentPosition.y, 
            z: z,
            feedrate 
        });
        // Clear input and update placeholder after move
        zInput.value = '';
        zInput.placeholder = `Current: ${z.toFixed(1)} mm`;
    }
    
    homeNozzle() {
        this.sendCommand('cmd.home_nozzle', {});
    }
    
    moveIncremental(axis, delta) {
        console.log(`moveIncremental called: axis=${axis}, delta=${delta}, currentPos=`, this.currentPosition);
        const newPos = { ...this.currentPosition };
        newPos[axis] = newPos[axis] + delta;
        
        // Clamp to safe limits
        const limits = {
            x: { min: this.config.x_min, max: this.config.x_max },
            y: { min: this.config.y_min, max: this.config.y_max },
            z: { min: this.config.z_min, max: this.config.z_max }
        };
        
        newPos[axis] = Math.max(limits[axis].min, Math.min(limits[axis].max, newPos[axis]));
        
        console.log(`Sending move command: axis=${axis}, from ${this.currentPosition[axis]} to ${newPos[axis]}, full pos:`, newPos);
        
        const feedrate = this.config.move_feedrate_default || 1500;
        this.sendCommand('cmd.move_nozzle', {
            x: newPos.x,
            y: newPos.y,
            z: newPos.z,
            feedrate: feedrate
        });
    }
    
    emergencyStop() {
        if (confirm('Are you sure you want to activate emergency stop?')) {
            this.sendCommand('cmd.emergency_stop', {});
        }
    }
    
    async captureImage() {
        try {
            const response = await fetch('/capture', { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                alert(`Image captured: ${data.filename}`);
            } else {
                alert(`Capture failed: ${data.error}`);
            }
        } catch (error) {
            alert(`Capture error: ${error.message}`);
        }
    }
    
    sendCommand(command, data) {
        if (!this.socket || !this.socket.connected) {
            alert('Not connected to server. Please wait for connection...');
            return;
        }
        
        // Check if this is a movement command
        const isMovementCommand = command.startsWith('cmd.move_') || command === 'cmd.home_nozzle';
        if (isMovementCommand && this.moving) {
            alert('Movement in progress. Please wait for the current movement to complete.');
            return;
        }
        
        console.log('Sending command:', command, data);
        this.socket.emit(command, data);
        this.lastCommand = { command, data, timestamp: Date.now() };
        this.updateLastCommand();
        
        // Set moving state for movement commands
        if (isMovementCommand) {
            this.moving = true;
            this.updateMovementButtons();
        }
    }
    
    updateTelemetry(data) {
        // Update current position - hardware should now report positions correctly
        // after the swap is handled in the hardware layer
        this.currentPosition = {
            x: data.nozzle.x,
            y: data.nozzle.y,
            z: data.nozzle.z
        };
        
        // Update nozzle position display
        document.getElementById('nozzle-x').textContent = data.nozzle.x.toFixed(1);
        document.getElementById('nozzle-y').textContent = data.nozzle.y.toFixed(1);
        document.getElementById('nozzle-z').textContent = data.nozzle.z.toFixed(1);
        
        // Update input field placeholders with current position (if empty)
        const xInput = document.getElementById('nozzle-x-input');
        const yInput = document.getElementById('nozzle-y-input');
        const zInput = document.getElementById('nozzle-z-input');
        
        // Always update placeholders to show current position when input is empty
        if (xInput && !xInput.value) {
            xInput.placeholder = `Current: ${data.nozzle.x.toFixed(1)} mm`;
        }
        if (yInput && !yInput.value) {
            yInput.placeholder = `Current: ${data.nozzle.y.toFixed(1)} mm`;
        }
        if (zInput && !zInput.value) {
            zInput.placeholder = `Current: ${data.nozzle.z.toFixed(1)} mm`;
        }
        
        // Update 3D visualization
        this.updateVisualization();
        
        // Update system status
        const previousStatus = this.systemStatus;
        this.systemStatus = data.status;
        this.updateSystemStatus();
        
        // Update movement state based on system status
        // This is the primary source of truth for movement state
        if (this.systemStatus === 'moving') {
            if (!this.moving) {
                console.log('System status changed to moving - disabling buttons');
                this.moving = true;
                this.updateMovementButtons();
            }
        } else if (this.systemStatus === 'idle') {
            if (this.moving) {
                console.log('System status changed to idle - enabling buttons');
                this.moving = false;
                this.updateMovementButtons();
            }
        }
    }
    
    waitForThreeAndInit(maxAttempts = 50) {
        // Prevent multiple calls
        if (this._waitingForThree) {
            console.log('Already waiting for THREE.js, skipping duplicate call');
            return;
        }
        
        console.log(`waitForThreeAndInit called, THREE defined: ${typeof THREE !== 'undefined'}, attempts: ${maxAttempts}`);
        
        if (typeof THREE !== 'undefined') {
            this._waitingForThree = false;
            console.log('THREE.js is available, version:', THREE.REVISION);
            console.log('Scheduling visualization initialization in 100ms...');
            // Use a small delay to ensure container is rendered
            setTimeout(() => {
                console.log('Timeout fired, calling initializeVisualization...');
                this.initializeVisualization();
            }, 100);
        } else if (maxAttempts > 0) {
            this._waitingForThree = true;
            console.log(`Waiting for THREE.js... (${maxAttempts} attempts remaining)`);
            setTimeout(() => {
                this._waitingForThree = false;
                this.waitForThreeAndInit(maxAttempts - 1);
            }, 100);
        } else {
            this._waitingForThree = false;
            console.error('THREE.js failed to load after 5 seconds! Visualization will not work.');
            // Try anyway - maybe it loaded but check failed
            console.log('Attempting to initialize anyway...');
            setTimeout(() => {
                this.initializeVisualization();
            }, 100);
        }
    }
    
    initializeVisualization() {
        // Prevent duplicate initialization
        if (this._visualizationInitialized) {
            console.log('Visualization already initialized, skipping...');
            return;
        }
        
        console.log('=== Starting visualization initialization ===');
        const container = document.getElementById('visualization-container');
        if (!container) {
            console.error('Cannot find visualization-container element!');
            const errorDiv = document.createElement('div');
            errorDiv.style.cssText = 'padding: 20px; color: red; background: #ffe0e0; border: 2px solid red;';
            errorDiv.textContent = 'ERROR: visualization-container element not found!';
            document.body.appendChild(errorDiv);
            return;
        }
        console.log('Container found:', container);
        
        if (!this.config) {
            console.error('Config not loaded yet!');
            container.innerHTML = '<div style="padding: 20px; color: red;">Config not loaded yet!</div>';
            return;
        }
        console.log('Config loaded:', this.config);
        
        // Check if THREE is loaded
        if (typeof THREE === 'undefined') {
            console.error('THREE.js is not loaded! Check if the script tag is correct.');
            container.innerHTML = '<div style="padding: 20px; color: red;">THREE.js not loaded! Check browser console.</div>';
            return;
        }
        console.log('THREE.js version:', THREE.REVISION);
        
        try {
        
        console.log('Initializing visualization with config:', this.config);
        console.log('Container size:', container.clientWidth, 'x', container.clientHeight);
        console.log('Container computed style:', window.getComputedStyle(container).width, 'x', window.getComputedStyle(container).height);
        
        // Make sure container has a size - force it if needed
        let width = container.clientWidth;
        let height = container.clientHeight;
        
        if (width === 0 || height === 0) {
            console.warn('Container has zero size! Setting default size.');
            // Try to get size from computed style
            const computedStyle = window.getComputedStyle(container);
            const computedWidth = parseInt(computedStyle.width);
            const computedHeight = parseInt(computedStyle.height);
            
            if (computedWidth > 0 && computedHeight > 0) {
                width = computedWidth;
                height = computedHeight;
                console.log('Using computed size:', width, 'x', height);
            } else {
                // Force a size
                container.style.width = '400px';
                container.style.height = '400px';
                width = 400;
                height = 400;
                console.log('Forced container size to:', width, 'x', height);
            }
        }
        
        // Scene setup
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0xf0f0f0);
        
        // Calculate workspace dimensions once
        // Coordinate mapping: Printer (X, Y, Z) -> Three.js (x, -z, y)
        // So: Printer X -> Three.js x, Printer Y -> Three.js -z, Printer Z -> Three.js y
        const workspaceWidth = this.config.x_max - this.config.x_min;  // Printer X -> Three.js x
        const workspaceHeight = this.config.z_max - this.config.z_min; // Printer Z -> Three.js y
        const workspaceDepth = this.config.y_max - this.config.y_min;  // Printer Y -> Three.js z (will be negated)
        
        // Camera setup - use the width/height we determined above
        // Slightly wider FOV for a bit more zoom out
        this.camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 1000);
        
        // Calculate center of workspace
        // Coordinate mapping: Printer (X, Y, Z) -> Three.js (x, -z, y)
        const centerX = this.config.x_min + workspaceWidth / 2;
        const centerY = this.config.z_min + workspaceHeight / 2;  // Printer Z -> Three.js Y
        const centerZ = -(this.config.y_min + workspaceDepth / 2); // Printer Y -> Three.js -Z
        
        console.log('Workspace center:', { centerX, centerY, centerZ });
        
        // Position camera as if standing slightly to the side of printer, looking down at an angle
        // Front of printer is at Y=0 (which is -Z in Three.js, so we want positive Z)
        // Camera should be elevated but less steep than bird's eye view, with a side angle
        const maxDim = Math.max(workspaceWidth, workspaceHeight, workspaceDepth);
        
        // Camera position: slightly to the side and in front of printer, elevated, looking down
        // Front of printer: Y=0 in printer coords = -y_min in Three.js Z
        // Position camera slightly to the right (positive X) and in front
        const frontDistance = maxDim * 1.0;  // Distance in front of printer
        const sideOffset = maxDim * 0.3;     // Offset to the right side for angled view
        const elevation = maxDim * 0.8;      // Less elevation for a gentler viewing angle
        const camX = centerX + sideOffset;    // Offset to the right side
        const camY = centerY + elevation;     // Elevated above workspace
        const camZ = -(this.config.y_min) + frontDistance;  // In front of printer (positive Z in Three.js)
        
        this.camera.position.set(camX, camY, camZ);
        this.camera.lookAt(centerX, centerY, centerZ);
        console.log('Camera positioned at:', { x: camX, y: camY, z: camZ }, 'looking at:', { centerX, centerY, centerZ });
        
        // Renderer setup - enable antialiasing for better quality
        // Try to create WebGL renderer (will fail gracefully if WebGL not supported)
        try {
            this.renderer = new THREE.WebGLRenderer({ 
                antialias: true,  // Enable antialiasing for sharper edges
                alpha: false,
                powerPreference: "high-performance",
                precision: "highp"  // Use high precision for better quality
            });
            console.log('WebGL renderer created successfully');
        } catch (error) {
            console.error('Failed to create WebGL renderer:', error);
            // Try to check if WebGL is supported using a different method
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            if (!gl) {
                throw new Error('WebGL is not supported in this browser!');
            }
            throw new Error('Failed to create WebGL renderer: ' + error.message);
        }
        
        // Use device pixel ratio for high DPI displays
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2); // Cap at 2x for performance
        this.renderer.setPixelRatio(pixelRatio);
        this.renderer.setSize(width, height);
        this.renderer.setClearColor(0xf0f0f0, 1); // Light gray background
        const canvas = this.renderer.domElement;
        canvas.style.display = 'block'; // Make sure canvas is visible
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.position = 'relative'; // Ensure positioning
        canvas.style.margin = '0';
        canvas.style.padding = '0';
        
        // Clear any existing content in container
        container.innerHTML = '';
        container.appendChild(canvas);
        
        console.log('Renderer created and added to container, size:', width, 'x', height);
        
        // Initialize OrbitControls for interactive camera (after renderer is created and canvas is in DOM)
        try {
            if (typeof THREE !== 'undefined' && typeof THREE.OrbitControls !== 'undefined' && this.renderer && this.renderer.domElement) {
                this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
                this.controls.target.set(centerX, centerY, centerZ);
                this.controls.enableDamping = true; // Smooth camera movement
                this.controls.dampingFactor = 0.05;
                this.controls.minDistance = maxDim * 0.5; // Minimum zoom distance
                this.controls.maxDistance = maxDim * 3;   // Maximum zoom distance
                this.controls.enablePan = true; // Allow panning
                this.controls.update();
                console.log('OrbitControls initialized successfully');
            } else {
                console.warn('OrbitControls not loaded or renderer not ready - interactive controls disabled. Mouse controls will not work.');
                this.controls = null;
            }
        } catch (error) {
            console.error('Failed to initialize OrbitControls:', error);
            this.controls = null;
        }
        console.log('Canvas element:', canvas);
        console.log('Canvas in DOM:', container.contains(canvas));
        console.log('Canvas dimensions:', canvas.width, 'x', canvas.height);
        console.log('Canvas style:', canvas.style.cssText);
        console.log('Container computed style:', window.getComputedStyle(container).display);
        
        // Add lights
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        this.scene.add(ambientLight);
        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.4);
        directionalLight.position.set(1, 1, 1);
        this.scene.add(directionalLight);
        
        // Draw workspace bounds (wireframe box)
        // Coordinate mapping: Printer (X, Y, Z) -> Three.js (x, -z, y)
        // Origin (0,0,0) is at front-left-bottom corner
        
        console.log('Creating wireframe box:', { workspaceWidth, workspaceHeight, workspaceDepth });
        
        // Create box geometry: width (X), height (Z), depth (Y)
        // In Three.js: x=width, y=height, z=depth
        // Mapping: Printer X->x, Printer Z->y, Printer Y->z (negated)
        const workspaceGeometry = new THREE.BoxGeometry(workspaceWidth, workspaceHeight, workspaceDepth);
        const workspaceEdges = new THREE.EdgesGeometry(workspaceGeometry);
        const workspaceMaterial = new THREE.LineBasicMaterial({ 
            color: 0x0000ff,  // Blue wireframe for workspace bounds
            linewidth: 2,
            linecap: 'round',
            linejoin: 'round'
        });
        this.workspaceBox = new THREE.LineSegments(workspaceEdges, workspaceMaterial);
        
        // Position box so it represents the workspace bounds
        // Box center should be at the workspace center in Three.js coordinates
        const boxPosX = this.config.x_min + workspaceWidth / 2;
        const boxPosY = this.config.z_min + workspaceHeight / 2;  // Printer Z -> Three.js Y
        const boxPosZ = -(this.config.y_min + workspaceDepth / 2); // Printer Y -> Three.js -Z
        this.workspaceBox.position.set(boxPosX, boxPosY, boxPosZ);
        console.log('Wireframe box positioned at:', { x: boxPosX, y: boxPosY, z: boxPosZ });
        this.scene.add(this.workspaceBox);
        
        // Add GridHelper to represent the bed (XY plane at Z=0)
        // GridHelper by default lies in the XZ plane (horizontal floor)
        // In our coordinate mapping: Printer (X, Y, Z) -> Three.js (x, -z, y)
        // So printer XY plane (bed) maps to Three.js XZ plane (which GridHelper uses by default)
        const gridSize = Math.max(workspaceWidth, workspaceDepth); // Use X and Y dimensions
        const gridDivisions = 10; // Reduced from 20 for better performance
        const gridHelper = new THREE.GridHelper(gridSize, gridDivisions, 0x888888, 0xcccccc);
        // Position grid at bed level (printer Z=0)
        // In Three.js: X = printer X, Y = printer Z, Z = -printer Y
        // Bed is at printer Z=0, so Three.js Y = 0 (which is z_min)
        gridHelper.position.set(
            this.config.x_min + workspaceWidth / 2,  // Center in X
            this.config.z_min,  // Bed is at printer Z=0 -> Three.js Y=z_min
            -(this.config.y_min + workspaceDepth / 2)  // Center in Z (negated Y)
        );
        // No rotation needed - GridHelper already lies in XZ plane (horizontal)
        this.scene.add(gridHelper);
        
        // Add axes helper at origin (0, 0, 0)
        const axesSize = Math.max(workspaceWidth, workspaceHeight, workspaceDepth) * 0.3;
        const axesHelper = new THREE.AxesHelper(axesSize);
        // Position at origin: Printer (0,0,0) -> Three.js (x_min, z_min, -y_min)
        axesHelper.position.set(
            this.config.x_min,   // X: printer X=0 -> Three.js x=0
            this.config.z_min,   // Y: printer Z=0 -> Three.js y=0
            -this.config.y_min   // Z: printer Y=0 -> Three.js z=0 (negated)
        );
        this.scene.add(axesHelper);
        
        // Add origin marker (green sphere at 0,0,0) - this is the homed position
        // The origin corresponds to where the nozzle moves to when homed
        const originGeometry = new THREE.SphereGeometry(4, 16, 12);  // Green dot size
        const originMaterial = new THREE.MeshBasicMaterial({ 
            color: 0x00ff00,
            transparent: true,
            opacity: 0.8
        });
        const originMarker = new THREE.Mesh(originGeometry, originMaterial);
        // Position at origin: Printer (0,0,0) -> Three.js (x_min, z_min, -y_min)
        originMarker.position.set(
            this.config.x_min,   // X: printer X=0 -> Three.js x=x_min
            this.config.z_min,   // Y: printer Z=0 -> Three.js y=z_min
            -this.config.y_min   // Z: printer Y=0 -> Three.js z=-y_min (negated)
        );
        this.scene.add(originMarker);
        console.log('Origin marker (green sphere) added at:', originMarker.position);
        
        // Create nozzle marker (red sphere) - make it bigger than green dot
        const nozzleGeometry = new THREE.SphereGeometry(6, 16, 12);  // Red dot is bigger (6 vs 4)
        const nozzleMaterial = new THREE.MeshBasicMaterial({ 
            color: 0xff0000,
            transparent: true,
            opacity: 0.9
        });
        this.nozzleMarker = new THREE.Mesh(nozzleGeometry, nozzleMaterial);
        this.scene.add(this.nozzleMarker);
        
        // Add dimension labels to wireframe corners
        this.addDimensionLabels(workspaceWidth, workspaceHeight, workspaceDepth);
        
        // Handle window resize
        window.addEventListener('resize', () => {
            const newWidth = container.clientWidth;
            const newHeight = container.clientHeight;
            const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
            this.camera.aspect = newWidth / newHeight;
            this.camera.updateProjectionMatrix();
            this.renderer.setPixelRatio(pixelRatio);
            this.renderer.setSize(newWidth, newHeight);
            this.requestRender();
        });
        
        // Initial render - do it immediately
        console.log('Performing initial render...');
        console.log('Scene children count:', this.scene.children.length);
        console.log('Scene children:', this.scene.children.map(c => c.type || c.constructor.name));
        
        if (this.renderer && this.scene && this.camera) {
            // Render multiple times to ensure visibility
            for (let i = 0; i < 3; i++) {
                this.renderer.render(this.scene, this.camera);
                console.log(`Render ${i + 1} complete`);
            }
            
            // Verify canvas is actually in DOM and visible
            const canvas = this.renderer.domElement;
            const rect = canvas.getBoundingClientRect();
            console.log('Canvas bounding rect:', rect);
            console.log('Canvas visible:', rect.width > 0 && rect.height > 0);
            
            // Force a render after a brief delay
            setTimeout(() => {
                if (this.renderer && this.scene && this.camera) {
                    this.renderer.render(this.scene, this.camera);
                    console.log('Delayed render complete');
                }
            }, 200);
        } else {
            console.error('Cannot render - missing components:', {
                renderer: !!this.renderer,
                scene: !!this.scene,
                camera: !!this.camera
            });
            container.innerHTML = '<div style="padding: 20px; color: red;">Failed to create renderer/scene/camera. Check console.</div>';
        }
        
        // Set up on-demand render loop (only renders when needed)
        // But always render on the first frame to ensure visibility
        let firstFrame = true;
        const animate = () => {
            this.animationFrameId = requestAnimationFrame(animate);
            
            // Update OrbitControls if available (for smooth interaction)
            if (this.controls) {
                this.controls.update();
                // Always render when controls are active
                if (this.renderer && this.scene && this.camera) {
                    this.renderer.render(this.scene, this.camera);
                    this.needsRender = false;
                    if (firstFrame) {
                        firstFrame = false;
                        console.log('First animation frame rendered');
                    }
                }
            } else if ((this.needsRender || firstFrame) && this.renderer && this.scene && this.camera) {
                // Only render when needed if no controls
                this.renderer.render(this.scene, this.camera);
                this.needsRender = false;
                if (firstFrame) {
                    firstFrame = false;
                    console.log('First animation frame rendered');
                }
            }
        };
        animate();
        console.log('Started on-demand animation loop');
        
        // Also update visualization if nozzle marker exists
        if (this.nozzleMarker) {
            this.updateVisualization();
        }
        
        this._visualizationInitialized = true;
        console.log('Visualization initialization complete!');
        } catch (error) {
            console.error('Error initializing visualization:', error);
            console.error(error.stack);
            // Show user-friendly error message
            const container = document.getElementById('visualization-container');
            if (container) {
                container.innerHTML = '<div style="padding: 20px; color: red;">Error loading 3D visualization. Please check the browser console for details.</div>';
            }
            this._visualizationInitialized = true; // Mark as attempted even on error
        }
    }
    
    addDimensionLabels(width, height, depth) {
        // Create text sprites for dimension labels
        // We'll use canvas-based text since TextGeometry requires a font loader
        
        const createTextSprite = (text, position, color = 0x000000, backgroundColor = 0xffffff, vertical = false, isMaxLabel = false) => {
            // Use high resolution canvas for crisp text
            const scale = 4; // 4x resolution for very sharp text
            const padding = isMaxLabel ? 12 : 16;
            const canvas = document.createElement('canvas');
            const context = canvas.getContext('2d');
            
            // Measure text first to size canvas appropriately
            const fontSize = isMaxLabel ? 16 : 20;
            context.font = `${isMaxLabel ? '500' : '600'} ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`;
            const metrics = context.measureText(text);
            const textWidth = metrics.width;
            const textHeight = fontSize;
            
            // For vertical text, swap dimensions
            const canvasWidth = vertical ? (textHeight + padding * 2) : (textWidth + padding * 2);
            const canvasHeight = vertical ? (textWidth + padding * 2) : (textHeight + padding * 2);
            
            canvas.width = canvasWidth * scale;
            canvas.height = canvasHeight * scale;
            
            // Scale up the context for high DPI rendering
            context.scale(scale, scale);
            
            // Rotate canvas if vertical (rotate clockwise)
            if (vertical) {
                context.translate(canvasWidth / 2, canvasHeight / 2);
                context.rotate(-Math.PI / 2);
                context.translate(-canvasHeight / 2, -canvasWidth / 2);
            }
            
            // Draw background with subtle shadow and modern styling
            const bgR = (backgroundColor >> 16) & 0xFF;
            const bgG = (backgroundColor >> 8) & 0xFF;
            const bgB = backgroundColor & 0xFF;
            
            // Create subtle gradient background
            const gradient = context.createLinearGradient(0, 0, 0, canvasHeight);
            gradient.addColorStop(0, `rgba(${bgR}, ${bgG}, ${bgB}, 0.95)`);
            gradient.addColorStop(1, `rgba(${bgR}, ${bgG}, ${bgB}, 0.9)`);
            
            const cornerRadius = 8;
            const x = padding / 2;
            const y = padding / 2;
            const w = textWidth + padding;
            const h = textHeight + padding;
            
            // Helper function to draw rounded rectangle
            const drawRoundedRect = (ctx, x, y, w, h, radius) => {
                ctx.beginPath();
                ctx.moveTo(x + radius, y);
                ctx.lineTo(x + w - radius, y);
                ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
                ctx.lineTo(x + w, y + h - radius);
                ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
                ctx.lineTo(x + radius, y + h);
                ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
                ctx.lineTo(x, y + radius);
                ctx.quadraticCurveTo(x, y, x + radius, y);
                ctx.closePath();
            };
            
            // Draw subtle shadow first
            context.fillStyle = 'rgba(0, 0, 0, 0.15)';
            drawRoundedRect(context, x + 1, y + 2, w, h, cornerRadius);
            context.fill();
            
            // Draw background with gradient
            context.fillStyle = gradient;
            drawRoundedRect(context, x, y, w, h, cornerRadius);
            context.fill();
            
            // Draw subtle border (lighter for max labels)
            const borderColor = isMaxLabel 
                ? `rgba(${(color >> 16) & 0xFF}, ${(color >> 8) & 0xFF}, ${color & 0xFF}, 0.2)`
                : `rgba(${(color >> 16) & 0xFF}, ${(color >> 8) & 0xFF}, ${color & 0xFF}, 0.3)`;
            context.strokeStyle = borderColor;
            context.lineWidth = 1.5;
            drawRoundedRect(context, x, y, w, h, cornerRadius);
            context.stroke();
            
            // Draw text with better color and no shadow for cleaner look
            const textR = (color >> 16) & 0xFF;
            const textG = (color >> 8) & 0xFF;
            const textB = color & 0xFF;
            context.fillStyle = `rgba(${textR}, ${textG}, ${textB}, 0.9)`;
            context.font = `${isMaxLabel ? '500' : '600'} ${fontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`;
            context.textAlign = 'center';
            context.textBaseline = 'middle';
            context.fillText(text, (textWidth + padding) / 2 + padding / 2, (textHeight + padding) / 2 + padding / 2);
            
            const texture = new THREE.CanvasTexture(canvas);
            texture.minFilter = THREE.LinearFilter;
            texture.magFilter = THREE.LinearFilter;
            texture.generateMipmaps = false;
            
            const spriteMaterial = new THREE.SpriteMaterial({ 
                map: texture,
                transparent: true,
                alphaTest: 0.01,
                depthTest: false,
                depthWrite: false
            });
            const sprite = new THREE.Sprite(spriteMaterial);
            
            // Adjust scale based on orientation
            if (vertical) {
                sprite.scale.set(35, 140, 1);
            } else {
                sprite.scale.set(140, 35, 1);
            }
            
            sprite.position.copy(position);
            return sprite;
        };
        
        // Add professional dimension labels at key positions
        // Strategically positioned to avoid overlaps with rotations where needed
        // Use white background with colored borders for professional look
        
        // Origin label - modern, subtle styling
        const originLabel = createTextSprite(
            `Origin (0,0,0)`,
            new THREE.Vector3(
                this.config.x_min - 18,
                this.config.z_min - 6,
                -this.config.y_min - 18
            ),
            0x2d8659,  // Softer green
            0xffffff,  // White background
            false,
            false
        );
        this.scene.add(originLabel);
        
        // Dimensions tuple label in corner - shows (X, Y, Z) dimensions
        const dimensionsLabel = createTextSprite(
            `(${width.toFixed(0)}, ${depth.toFixed(0)}, ${height.toFixed(0)}) mm`,
            new THREE.Vector3(
                this.config.x_max + 20,
                this.config.z_max + 15,
                -this.config.y_max - 8
            ),
            0x4a5568,  // Dark gray
            0xffffff,  // White background
            false,
            false
        );
        this.scene.add(dimensionsLabel);
    }
    
    requestRender() {
        // Mark that a render is needed
        this.needsRender = true;
    }
    
    updateVisualization() {
        if (!this.nozzleMarker || !this.renderer || !this.scene || !this.camera) {
            console.warn('Cannot update visualization - missing components', {
                nozzleMarker: !!this.nozzleMarker,
                renderer: !!this.renderer,
                scene: !!this.scene,
                camera: !!this.camera
            });
            return;
        }
        
        // Update nozzle marker position
        // Coordinate mapping: Printer (X, Y, Z) -> Three.js (x, -z, y)
        // Origin (homed position) is at printer (x_min, y_min, z_min) = (0, 0, 0)
        // So we offset by those values to position relative to the origin
        const newX = this.config.x_min + this.currentPosition.x;
        const newY = this.config.z_min + this.currentPosition.z;
        const newZ = -(this.config.y_min + this.currentPosition.y);
        
        this.nozzleMarker.position.set(newX, newY, newZ);
        
        console.log('Updated nozzle marker position:', { x: newX, y: newY, z: newZ, currentPos: this.currentPosition });
        
        // Force immediate render to ensure update is visible
        if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
        
        // Also request render for animation loop
        this.requestRender();
    }
    
    handleCommandAck(data) {
        console.log('Command ACK:', data);
        
        // Check if this was a movement command
        const isMovementCommand = this.lastCommand && (
            this.lastCommand.command.startsWith('cmd.move_') || 
            this.lastCommand.command === 'cmd.home_nozzle'
        );
        
        // Update UI based on command status
        if (data.status === 'ok') {
            console.log('Command completed successfully');
            // Clear moving state when movement command completes
            // But don't clear if system status is still 'moving' (wait for telemetry)
            if (isMovementCommand && this.systemStatus !== 'moving') {
                console.log('Clearing moving state - command completed and system idle');
                this.moving = false;
                this.updateMovementButtons();
            } else if (isMovementCommand) {
                console.log('Command completed but system still moving - waiting for telemetry');
            }
        } else if (data.status === 'err') {
            console.error('Command failed:', data.message);
            alert(`Command failed: ${data.message}`);
            // Always clear moving state on error
            if (isMovementCommand) {
                console.log('Clearing moving state due to error');
                this.moving = false;
                this.updateMovementButtons();
            }
        }
        
        this.lastCommand = { ...this.lastCommand, ack: data };
        this.updateLastCommand();
    }
    
    updateMovementButtons() {
        // Get all movement-related buttons
        const movementButtons = [
            'home-nozzle-btn',
            'move-x-btn',
            'move-y-btn',
            'move-z-btn',
            'x-plus-btn', 'x-minus-btn',
            'y-plus-btn', 'y-minus-btn',
            'z-plus-btn', 'z-minus-btn'
        ];
        
        movementButtons.forEach(btnId => {
            const btn = document.getElementById(btnId);
            if (btn) {
                btn.disabled = this.moving;
            }
        });
    }
    
    updateConnectionStatus() {
        const statusElement = document.getElementById('connection-status');
        if (this.connected) {
            statusElement.textContent = 'Connected';
            statusElement.className = 'status-connected';
        } else {
            statusElement.textContent = 'Disconnected';
            statusElement.className = 'status-disconnected';
        }
    }
    
    updateSystemStatus() {
        const statusElement = document.getElementById('system-status');
        statusElement.textContent = this.systemStatus.charAt(0).toUpperCase() + this.systemStatus.slice(1);
        statusElement.className = `status-${this.systemStatus}`;
    }
    
    updateLastCommand() {
        const lastCommandElement = document.getElementById('last-command');
        if (this.lastCommand) {
            const time = new Date(this.lastCommand.timestamp).toLocaleTimeString();
            lastCommandElement.textContent = `${this.lastCommand.command} at ${time}`;
        } else {
            lastCommandElement.textContent = 'None';
        }
    }
    
    updateUI() {
        this.updateConnectionStatus();
        this.updateSystemStatus();
        this.updateLastCommand();
        this.updateMovementButtons();
    }
}

// Wait for Three.js to load before initializing
function waitForThreeJS(callback, maxAttempts = 20) {
    console.log(`waitForThreeJS: THREE defined = ${typeof THREE !== 'undefined'}, attempts = ${maxAttempts}`);
    if (typeof THREE !== 'undefined') {
        console.log('Three.js is available, version:', THREE.REVISION);
        callback();
    } else if (maxAttempts > 0) {
        setTimeout(() => waitForThreeJS(callback, maxAttempts - 1), 100);
    } else {
        console.error('Three.js failed to load after 2 seconds!');
        console.log('Attempting to initialize anyway - THREE might load later...');
        // Still try to initialize, but visualization will fail gracefully
        callback();
    }
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, waiting for Three.js...');
    console.log('THREE at DOMContentLoaded:', typeof THREE);
    waitForThreeJS(() => {
        console.log('Initializing PrinterInterface...');
        console.log('THREE at initialization:', typeof THREE);
        try {
            window.printerInterface = new PrinterInterface();
            console.log('PrinterInterface created successfully');
        } catch (error) {
            console.error('Failed to create PrinterInterface:', error);
            console.error(error.stack);
        }
    });
});
