#!/usr/bin/env python3
import os
import time
import datetime
import threading
import cv2
import signal
import numpy as np
from flask import Flask, Response, jsonify, render_template, request
from flask_socketio import SocketIO
from picamera2 import Picamera2
from gpiozero import MotionSensor, Buzzer
from telegram import Bot
from telegram.error import TelegramError

# ===== Configuration =====
PIR_PIN = 17          # BCM17 (Physical Pin 11)
BUZZER_PIN = 18       # BCM18 (Physical Pin 12)
TELEGRAM_TOKEN = "7856984447:AAHLk7zu6mFjYK1_n3VUKoqwPxLfSPe-pJw"  # Replace with your actual token
TELEGRAM_CHAT_ID = "1162258333"  # Replace with your actual chat ID
RESOLUTION = (640, 480)
FPS = 30
RECORD_DURATION = 180  # 3 minutes in seconds
COOLDOWN_TIME = 300    # 5 minutes in seconds
OUTPUT_DIR = "recordings"

# ===== Hardware Initialization =====
def init_hardware():
    """Initialize hardware with proper cleanup handling"""
    global pir, buzzer, using_gpiozero
    
    # Release any existing GPIO resources
    os.system('sudo pkill pigpiod 2>/dev/null')
    time.sleep(1)
    
    try:
        pir = MotionSensor(PIR_PIN)
        buzzer = Buzzer(BUZZER_PIN)
        print("Using GPIOZero for hardware control")
        using_gpiozero = True
    except Exception as e:
        print(f"GPIOZero failed ({e}), using direct GPIO")
        import RPi.GPIO as GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(BUZZER_PIN, GPIO.OUT)
        using_gpiozero = False
    return using_gpiozero

# ===== Camera Initialization =====
def init_camera():
    """Initialize camera with resource conflict handling"""
    try:
        # Release camera resources if held by another process
        os.system('sudo pkill libcamera 2>/dev/null')
        time.sleep(2)
        
        picam2 = Picamera2()
        config = picam2.create_video_configuration(
            main={"size": RESOLUTION},
            controls={"FrameRate": FPS}
        )
        picam2.configure(config)
        picam2.start()
        time.sleep(2)  # Camera warm-up
        print("Camera initialized successfully")
        return picam2
    except Exception as e:
        print(f"Camera initialization failed: {e}")
        return None

# ===== Initialize Components =====
using_gpiozero = init_hardware()
picam2 = init_camera()
bot = None
if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        print("Telegram bot initialized successfully")
    except TelegramError as e:
        print(f"Failed to initialize Telegram bot: {e}")
        bot = None

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== Flask Setup =====
app = Flask(__name__)
socketio = SocketIO(app)

# ===== Global Variables =====
motion_enabled = True
recording = False
motion_count = 0
system_start_time = time.time()

# ===== Video Streaming =====
def generate_frames():
    while True:
        try:
            if picam2:
                frame = picam2.capture_array("main")
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                # Fallback test pattern
                frame = np.zeros((480, 640, 3), np.uint8)
                cv2.putText(frame, "CAMERA OFFLINE", (120, 240), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            # Add timestamp
            cv2.putText(frame, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
            
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        except Exception as e:
            print(f"Frame error: {e}")
            time.sleep(1)

# ===== Core Functions =====
def trigger_alarm(duration=5):
    """Control buzzer based on initialization method"""
    if using_gpiozero:
        buzzer.on()
        time.sleep(duration)
        buzzer.off()
    else:
        import RPi.GPIO as GPIO
        GPIO.output(BUZZER_PIN, True)
        time.sleep(duration)
        GPIO.output(BUZZER_PIN, False)
    socketio.emit('new_alert', {
        'message': f'Alarm triggered for {duration} seconds',
        'type': 'danger'
    })

def record_video():
    global recording, motion_count
    recording = True
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"motion_{timestamp}.mp4")
    
    try:
        picam2.start_recording(filename)
        start_time = time.time()
        
        while (time.time() - start_time) < RECORD_DURATION and motion_enabled:
            time.sleep(0.1)
        
        picam2.stop_recording()
        
        if motion_enabled:
            motion_count += 1
            socketio.emit('update_stats', {
                'motion_count': motion_count,
                'uptime': int(time.time() - system_start_time)
            })
            
            if bot and os.path.exists(filename):
                try:
                    with open(filename, 'rb') as f:
                        bot.send_video(
                            chat_id=TELEGRAM_CHAT_ID,
                            video=f,
                            caption=f"🚨 Motion Detected ({timestamp})"
                        )
                    socketio.emit('new_alert', {
                        'message': 'Video sent to Telegram',
                        'type': 'success'
                    })
                except TelegramError as e:
                    print(f"Failed to send video to Telegram: {e}")
                    socketio.emit('new_alert', {
                        'message': 'Failed to send video to Telegram',
                        'type': 'danger'
                    })
    except Exception as e:
        print(f"Recording error: {e}")
        socketio.emit('new_alert', {
            'message': f'Recording failed: {str(e)}',
            'type': 'danger'
        })
    finally:
        recording = False

def motion_detection():
    """Main motion detection loop"""
    while True:
        try:
            motion_detected = pir.motion_detected if using_gpiozero else pir()
            if motion_detected and not recording and motion_enabled:
                socketio.emit('motion_alert')
                threading.Thread(target=record_video).start()
                threading.Thread(target=trigger_alarm).start()
                time.sleep(COOLDOWN_TIME)
            time.sleep(0.1)
        except Exception as e:
            print(f"Motion detection error: {e}")
            time.sleep(1)

# ===== Web Routes =====
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/snapshot')
def snapshot():
    try:
        if picam2:
            frame = picam2.capture_array("main")
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        else:
            frame = np.zeros((480, 640, 3), np.uint8)
            cv2.putText(frame, "CAMERA OFFLINE", (120, 240), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Add timestamp
        cv2.putText(frame, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
        
        _, buffer = cv2.imencode('.jpg', frame)
        return Response(buffer.tobytes(), mimetype='image/jpeg')
    except Exception as e:
        return str(e), 500

@app.route('/toggle_motion', methods=['POST'])
def toggle_motion():
    global motion_enabled
    motion_enabled = not motion_enabled
    socketio.emit('motion_toggle', {'enabled': motion_enabled})
    socketio.emit('new_alert', {
        'message': f'Motion detection {"enabled" if motion_enabled else "disabled"}',
        'type': 'info'
    })
    return jsonify({'status': 'success', 'motion_enabled': motion_enabled})

@app.route('/trigger_alarm', methods=['POST'])
def alarm_endpoint():
    try:
        duration = int(request.args.get('duration', 5))
        threading.Thread(target=trigger_alarm, args=(duration,)).start()
        return jsonify({'status': 'success', 'message': f'Alarm triggered for {duration} seconds'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ===== Cleanup Handler =====
def cleanup():
    print("\nCleaning up resources...")
    try:
        if picam2:
            picam2.stop_recording()
            picam2.close()
    except:
        pass
    
    try:
        if using_gpiozero:
            buzzer.off()
        else:
            import RPi.GPIO as GPIO
            GPIO.output(BUZZER_PIN, False)
            GPIO.cleanup()
    except:
        pass

# ===== Main Execution =====
if __name__ == '__main__':
    # Create templates directory if missing
    os.makedirs('templates', exist_ok=True)
    
    # Create default HTML interface if missing
    if not os.path.exists('templates/index.html'):
        with open('templates/index.html', 'w') as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Security Camera</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin: 0; padding: 20px; }
        .video-container { margin: 20px auto; max-width: 640px; background: #000; }
        button { padding: 10px 20px; margin: 10px; font-size: 16px; }
        .status { margin: 20px; padding: 10px; background: #f0f0f0; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>Live Security Camera</h1>
    <div class="video-container">
        <img src="/video_feed" width="640" height="480">
    </div>
    <div class="status">
        Motion Detection: <span id="motion-status">Active</span>
    </div>
    <div>
        <button onclick="fetch('/toggle_motion', {method: 'POST'})">
            Toggle Motion Detection
        </button>
        <button onclick="window.open('/snapshot')">
            Take Snapshot
        </button>
        <button onclick="fetch('/trigger_alarm', {method: 'POST'})">
            Test Alarm
        </button>
    </div>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script>
        const socket = io();
        socket.on('motion_toggle', data => {
            document.getElementById('motion-status').textContent = 
                data.enabled ? 'Active' : 'Disabled';
        });
    </script>
</body>
</html>""")

    # Start motion detection thread
    motion_thread = threading.Thread(target=motion_detection)
    motion_thread.daemon = True
    motion_thread.start()

    # Setup cleanup handlers
    signal.signal(signal.SIGINT, lambda s, f: cleanup())
    signal.signal(signal.SIGTERM, lambda s, f: cleanup())

    try:
        print(f"""
        ================================
          Raspberry Pi Security Camera
          Status: {'OPERATIONAL' if picam2 else 'FALLBACK MODE'}
          Resolution: {RESOLUTION[0]}x{RESOLUTION[1]} @ {FPS}FPS
          Telegram: {'ENABLED' if bot else 'DISABLED'}
          Access: http://{os.popen('hostname -I').read().strip()}:5000
        ================================
        """)
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    finally:
        cleanup()
