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
        
        this.initializeSocket();
        this.bindEvents();
        this.updateUI();
    }
    
    detectMode() {
        // Check URL port or mode indicator
        if (window.location.port === '5000') return 'local';
        if (window.location.port === '5001') return 'connected';
        
        // Check for mode in page title or data attribute
        const modeElement = document.querySelector('[data-mode]');
        if (modeElement) return modeElement.dataset.mode;
        
        return 'local'; // Default
    }
    
    initializeSocket() {
        const port = this.mode === 'local' ? 5000 : 5001;
        this.socket = io(`http://localhost:${port}`);
        
        this.socket.on('connect', () => {
            console.log('Connected to server');
            this.connected = true;
            this.updateConnectionStatus();
        });
        
        this.socket.on('disconnect', () => {
            console.log('Disconnected from server');
            this.connected = false;
            this.updateConnectionStatus();
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
    }
    
    bindEvents() {
        // Nozzle movement controls
        document.getElementById('move-nozzle-btn').addEventListener('click', () => {
            this.moveNozzle();
        });
        
        document.getElementById('move-xy-btn').addEventListener('click', () => {
            this.moveNozzleXY();
        });
        
        document.getElementById('move-z-btn').addEventListener('click', () => {
            this.moveNozzleZ();
        });
        
        // Zoom controls
        document.getElementById('home-zoom-btn').addEventListener('click', () => {
            this.homeZoom();
        });
        
        document.getElementById('zoom-in-btn').addEventListener('click', () => {
            this.zoomIn();
        });
        
        document.getElementById('zoom-out-btn').addEventListener('click', () => {
            this.zoomOut();
        });
        
        // Emergency stop
        document.getElementById('emergency-stop-btn').addEventListener('click', () => {
            this.emergencyStop();
        });
        
        // Camera capture
        document.getElementById('capture-btn').addEventListener('click', () => {
            this.captureImage();
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
        const controlRow = input.closest('.control-row');
        const button = controlRow.querySelector('button');
        if (button) {
            button.click();
        }
    }
    
    moveNozzle() {
        const x = parseFloat(document.getElementById('nozzle-x-input').value) || 0;
        const y = parseFloat(document.getElementById('nozzle-y-input').value) || 0;
        const z = parseFloat(document.getElementById('nozzle-z-input').value) || 0;
        const feedrate = 1500; // Default feedrate
        
        this.sendCommand('cmd.move_nozzle', { x, y, z, feedrate });
    }
    
    moveNozzleXY() {
        const x = parseFloat(document.getElementById('nozzle-xy-x-input').value) || 0;
        const y = parseFloat(document.getElementById('nozzle-xy-y-input').value) || 0;
        const feedrate = 1500;
        
        this.sendCommand('cmd.move_nozzle_xy', { x, y, feedrate });
    }
    
    moveNozzleZ() {
        const z = parseFloat(document.getElementById('nozzle-z-only-input').value) || 0;
        const feedrate = 1500;
        
        this.sendCommand('cmd.move_nozzle_z', { z, feedrate });
    }
    
    homeZoom() {
        this.sendCommand('cmd.zoom', { action: 'home' });
    }
    
    zoomIn() {
        const steps = parseInt(document.getElementById('zoom-steps-input').value) || 100;
        this.sendCommand('cmd.zoom', { action: 'in', value: steps });
    }
    
    zoomOut() {
        const steps = parseInt(document.getElementById('zoom-steps-input').value) || 100;
        this.sendCommand('cmd.zoom', { action: 'out', value: steps });
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
        if (!this.connected) {
            alert('Not connected to server');
            return;
        }
        
        console.log('Sending command:', command, data);
        this.socket.emit(command, data);
        this.lastCommand = { command, data, timestamp: Date.now() };
        this.updateLastCommand();
    }
    
    updateTelemetry(data) {
        // Update nozzle position
        document.getElementById('nozzle-x').textContent = data.nozzle.x.toFixed(1);
        document.getElementById('nozzle-y').textContent = data.nozzle.y.toFixed(1);
        document.getElementById('nozzle-z').textContent = data.nozzle.z.toFixed(1);
        
        // Update zoom position
        document.getElementById('zoom-position').textContent = data.zoom.s_prime_mm.toFixed(1);
        document.getElementById('zoom-magnification').textContent = data.zoom.magnification.toFixed(1);
        document.getElementById('zoom-percentage').textContent = data.zoom.pct.toFixed(1);
        
        // Update system status
        this.systemStatus = data.status;
        this.updateSystemStatus();
    }
    
    handleCommandAck(data) {
        console.log('Command ACK:', data);
        
        // Update UI based on command status
        if (data.status === 'ok') {
            console.log('Command completed successfully');
        } else if (data.status === 'err') {
            alert(`Command failed: ${data.message}`);
        }
        
        this.lastCommand = { ...this.lastCommand, ack: data };
        this.updateLastCommand();
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
        
        // Update zoom status
        const zoomStatusElement = document.getElementById('zoom-status');
        if (this.systemStatus === 'homing') {
            zoomStatusElement.textContent = 'Homing...';
        } else if (this.systemStatus === 'moving') {
            zoomStatusElement.textContent = 'Moving...';
        } else if (this.systemStatus === 'idle') {
            zoomStatusElement.textContent = 'Ready';
        } else {
            zoomStatusElement.textContent = this.systemStatus;
        }
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
    }
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.printerInterface = new PrinterInterface();
});
