# PROJECT_REQUIREMENTS.md

## Goal (one line)
Laptop → USB → Raspberry Pi Zero: web UI with live camera preview, high-res capture, buttons to move printer nozzle (XY) and zoom (move sensor on linear actuator), plus simple cartoon/status for nozzle and sensor positions.

---

## Core (minimal) features
- Live low-res preview stream from HQ Camera.  
- High-res still capture on demand.  
- Controls: `Zoom In`, `Zoom Out`, `Home Zoom`, `Move Nozzle (XY preset)`, `Move Nozzle Z`, `Emergency Stop`.  
- Cartoon/status panel showing nozzle X/Y/Z and sensor linear-actuator position (mm and percent).  
- Two server modes:
  - **local** — simulated hardware and telemetry, enforces same numeric limits as connected mode.  
  - **connected** — real Pi HQ camera + GPIO/driver control for zoom + direct serial G-code to printer.

---

## Minimal frameworks / libraries (explicit)
- **Python 3** runtime.  
- **Flask** — HTTP server and static UI.  
- **Flask-SocketIO** — realtime command/status channel (use `eventlet` backend).  
- **libcamera / picamera2** — capture preview and high-res stills on Pi HQ Camera.  
- **pigpio** (daemon + `python-pigpio`) — deterministic GPIO for step/dir or servo control of zoom actuator.  
- **pyserial** — direct serial/G-code communication to the printer controller (recommended — simplest integration).

> **Choice:** direct serial (pyserial + sending G-code) is the easier, minimal approach for printer control. OctoPrint is intentionally excluded to keep the stack minimal.  
> **Connection:** USB gadget networking (USB-only laptop ↔ Pi) is the required connection mode.

---

## Minimal hardware (summary)
- Raspberry Pi Zero with HQ Camera (IMX477) and chosen lens (C/CS mount).  
- Linear actuator (leadscrew + small stepper) or servo for sensor translation, driver (A4988/DRV/TMC), motor PSU.  
- Endstop switch for zoom homing.  
- Anycubic Kobra 2 Neo (printer) — USB connection for G-code/serial.  
- Emergency-stop accessible from outside.  
- USB feedthrough or short USB pigtail for laptop ↔ Pi connection.

---

## Required config parameters (must be present in `config.yml`)
Each parameter: `key` — `type` — `units` — `example`.

**Camera / optics**
- `camera.sensor_width` — `float` — `mm` — `6.29`  
- `camera.sensor_height` — `float` — `mm` — `4.71`  
- `camera.pixel_pitch` — `float` — `µm` — `3.76`  
- `lens.focal_length` — `float` — `mm` — `8.0`  
- `lens.nominal_bfl` — `float` — `mm` — `6.5`  # back focal length / flange spec

**Zoom actuator (sensor translation)**
- `zoom.max_s_prime` — `float` — `mm` — `TODO`  # **placeholder**: maximum image distance s' (sensor-to-lens) reachable — fill in for hardware  
- `zoom.min_s_prime` — `float` — `mm` — `16.0`  # minimum s' (near flange) — hardware limit  
- `zoom.steps_per_mm` — `float` — `steps/mm` — `200.0`  
- `zoom.home_switch_pin` — `int` — (GPIO pin) — `17`  
- `zoom.direction_increase` — `string` — `"away"` / `"toward"` — which direction increments s'  
- `zoom.travel_safe_margin` — `float` — `mm` — `1.0`  # software safety margin from mechanical endpoints

**Printer**
- `printer.serial_device` — `string` — path — `/dev/ttyUSB0`  
- `printer.safe_limits.x_min` — `float` — `mm` — `0.0`  
- `printer.safe_limits.x_max` — `float` — `mm` — `220.0`  
- `printer.safe_limits.y_min` — `float` — `mm` — `0.0`  
- `printer.safe_limits.y_max` — `float` — `mm` — `220.0`  
- `printer.safe_limits.z_min` — `float` — `mm` — `0.0`  
- `printer.safe_limits.z_max` — `float` — `mm` — `250.0`  
- `printer.move_feedrate_default` — `int` — `mm/min` — `1500`

**Streaming / capture**
- `stream.preview_width` — `int` — `px` — `640`  
- `stream.preview_height` — `int` — `px` — `480`  
- `stream.preview_fps` — `int` — `fps` — `5`  
- `capture.width` — `int` — `px` — `4056`  
- `capture.height` — `int` — `px` — `3040`

**Safety / operational**
- `emergency_stop.gpio_pin` — `int` — pin — `27`  
- `power.motor_supply_voltage` — `float` — `V` — `12.0`  
- `power.motor_supply_max_current` — `float` — `A` — `4.0`

> Implementation must refuse commands that would exceed any configured limits. The `zoom.max_s_prime` placeholder must be set before final deployment.

---

## Minimal API (endpoints & socket messages)
- `GET /` → UI.  
- `GET /stream` → MJPEG preview endpoint.  
- `POST /capture` → capture full-resolution image, returns filename/URL.  

**Socket messages (socket.io)**
- `cmd.zoom` `{action: "in"|"out"|"home"|"goto", value: <mm|steps>}`  
- `cmd.move_nozzle` `{x: <mm>, y: <mm>, z: <mm>, feedrate: <mm/min>}`  
- `cmd.move_nozzle_xy` `{x: <mm>, y: <mm>, feedrate: <mm/min>}`  
- `cmd.move_nozzle_z` `{z: <mm>, feedrate: <mm/min>}`  
- `cmd.emergency_stop` `{}`  
- `telemetry.position` `{nozzle: {x,y,z}, zoom: {s_prime_mm, magnification, pct}}` (server emits periodically)

---

## Required equations & optical note
- Thin-lens (focus):
  \[
  \frac{1}{f}=\frac{1}{s}+\frac{1}{s'}
  \]
- Magnification:
  \[
  M=\frac{s'}{f}-1
  \]
- Required image distance for target magnification:
  \[
  s' = f(M+1)
  \]

**Practical takeaway:** with a mechanical limit `zoom.max_s_prime`, achievable magnification is \(M_{\max}=\text{zoom.max\_s\_prime}/f-1\). Set `zoom.max_s_prime` (placeholder) to the real travel value and recompute M_max to choose focal length appropriately.

---

## Safety rules (must be enforced)
- Emergency stop must cut or disable motor-driver enable pin immediately.  
- Software enforces `printer.safe_limits` (x, y, z) and `zoom.min_s_prime` / `zoom.max_s_prime`. Reject out-of-range moves.  
- Homing required after boot (zoom) before any zoom moves allowed.  
- Motor power on separate supply; connect grounds; do not power motors from Pi 5V.

---

## Minimal install & run checklist
1. Flash Raspberry Pi OS Lite, enable camera + SSH.  
2. Install Python3 + pip; install: `flask`, `flask-socketio`, `eventlet`, `picamera2` (or `libcamera`), `pigpio`, `pyserial`.  
3. Configure `config.yml` (fill the `zoom.max_s_prime` placeholder).  
4. Start `pigpiod` and the Flask/SocketIO service (systemd unit recommended).  
5. Connect laptop to Pi using USB (USB gadget networking); open the UI in the laptop browser.  
6. In **local** mode, verify UI shows simulated telemetry and buttons; in **connected** mode, verify camera preview, homing sequence, a small zoom move, and a safe nozzle move.

---

## Minimal deliverables
- `server/` — Flask backend (local & connected modes) + socket handlers.  
- `ui/` — single-page HTML+JS (preview, buttons, cartoon/status).  
- `hw/` — minimal pigpio zoom controller + homing routine + pyserial printer wrapper.  
- `config.example.yml` — with every parameter above (including `zoom.max_s_prime: TODO`).  
- `README.md` — start instructions and safety checklist.

---

## Confirmed choices / final notes
- `zoom.max_s_prime` left as a **placeholder** — must be set before deployment.  
- **Printer control:** direct serial (pyserial + G-code) — chosen because it is the simplest minimal integration.  
- **Connection:** USB gadget networking (USB-only laptop ↔ Pi) — required/preferred.