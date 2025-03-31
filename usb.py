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
from gpiozero import MotionSensor, Buzzer

# Telegram imports with version compatibility
try:
    from telegram import Bot, Update
    try:
        # For v20.0+
        from telegram.ext import Application, CommandHandler, ContextTypes
        TELEGRAM_NEW = True
    except ImportError:
        # For v12.x-v13.x
        from telegram.ext import Updater, CommandHandler, CallbackContext
        TELEGRAM_NEW = False
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("[WARNING] python-telegram-bot not installed. Telegram features disabled.")

# ===== Configuration =====
PIR_PIN = 17          # BCM17 (Physical Pin 11)
BUZZER_PIN = 18       # BCM18 (Physical Pin 12)
TELEGRAM_TOKEN = "7856984447:AAHLk7zu6mFjYK1_n3VUKoqwPxLfSPe-pJw"
TELEGRAM_CHAT_ID = "1162258333"
RESOLUTION = (640, 480)
FPS = 30
RECORD_DURATION = 180  # 3 minutes in seconds
COOLDOWN_TIME = 300    # 5 minutes in seconds
OUTPUT_DIR = "recordings"
USB_CAMERA_INDEX = 0   # Typically 0 for first USB camera

# ===== Global Variables =====
motion_enabled = True
recording = False
motion_count = 0
system_start_time = time.time()
video_writer = None

# ===== Initialize Components =====
print("===== Initializing Security Camera System =====")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Hardware initialization
try:
    pir = MotionSensor(PIR_PIN)
    buzzer = Buzzer(BUZZER_PIN)
    using_gpiozero = True
    print("[SUCCESS] GPIO components initialized")
except Exception as e:
    print(f"[WARNING] GPIOZero failed: {e}")
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    using_gpiozero = False

# Camera initialization
camera = cv2.VideoCapture(USB_CAMERA_INDEX)
if not camera.isOpened():
    print("[ERROR] Failed to open USB camera")
    camera = None
else:
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
    camera.set(cv2.CAP_PROP_FPS, FPS)
    print(f"[SUCCESS] Camera initialized at {RESOLUTION[0]}x{RESOLUTION[1]} @ {FPS}FPS")

# Telegram bot initialization
bot = None
telegram_app = None
if TELEGRAM_AVAILABLE and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        if TELEGRAM_NEW:
            telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
        else:
            telegram_app = Updater(TELEGRAM_TOKEN, use_context=True)
        print("[SUCCESS] Telegram bot initialized")
    except Exception as e:
        print(f"[ERROR] Telegram bot initialization failed: {e}")
        bot = None
        telegram_app = None

# ===== Flask & SocketIO Setup =====
app = Flask(__name__)
socketio = SocketIO(app)

# ===== Video Streaming =====
def generate_frames():
    while True:
        try:
            if camera:
                ret, frame = camera.read()
                if not ret:
                    print("[WARNING] Frame capture failed")
                    time.sleep(1)
                    continue
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                frame = np.zeros((480, 640, 3), np.uint8)
                cv2.putText(frame, "CAMERA OFFLINE", (120, 240), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            # Add timestamp
            cv2.putText(frame, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
            
            if recording and video_writer:
                video_writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            
            _, buffer = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        except Exception as e:
            print(f"[ERROR] Frame generation: {e}")
            time.sleep(1)

# ===== Core Functions =====
def trigger_alarm(duration=5):
    """Control buzzer based on initialization method"""
    try:
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
    except Exception as e:
        print(f"[ERROR] Alarm trigger failed: {e}")

def record_video():
    global recording, motion_count, video_writer
    recording = True
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H:%M:%S")
    filename = f"{OUTPUT_DIR}/motion_{timestamp}.mp4"
    
    # Use MP4V codec with proper settings
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(
        filename,
        fourcc,
        FPS, 
        RESOLUTION,
        isColor=True
    )
    
    if not video_writer.isOpened():
        print("Error: Could not open video writer")
        recording = False
        return
    
    print(f"Started recording: {filename}")
    start_time = time.time()
    
    try:
        while (time.time() - start_time) < RECORD_DURATION and motion_enabled:
            ret, frame = camera.read()
            if not ret:
                print("Error: Failed to capture frame")
                break
                
            video_writer.write(frame)
            time.sleep(1/FPS)  # Maintain frame rate
            
    except Exception as e:
        print(f"Recording error: {e}")
    
    finally:
        # Properly release the video writer
        if video_writer:
            video_writer.release()
            print(f"Finished recording: {filename}")
            
            # Verify file was created
            if os.path.exists(filename):
                print(f"File size: {os.path.getsize(filename)/1024:.1f} KB")
                
                # Send via Telegram
                if bot:
                    try:
                        with open(filename, 'rb') as video_file:
                            bot.send_video(
                                chat_id=TELEGRAM_CHAT_ID,
                                video=video_file,
                                caption=f"Motion detected at {timestamp}",
                                supports_streaming=True,
                                timeout=20
                            )
                        print("Video sent successfully via Telegram")
                    except Exception as e:
                        print(f"Failed to send video: {e}")
                    
                    # Clean up
                    try:
                        os.remove(filename)
                    except:
                        pass
            else:
                print("Error: Recorded file not found")
        
        recording = False
        video_writer = None
        motion_count += 1
        socketio.emit('motion_recorded', {'count': motion_count})

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
            print(f"[ERROR] Motion detection: {e}")
            time.sleep(1)

# ===== Telegram Bot Functions =====
def start(update, context):
    """Send welcome message when /start is issued"""
    update.message.reply_text(
        "🚨 Raspberry Pi Security Bot Activated 🚨\n\n"
        "Available commands:\n"
        "/status - Get system status\n"
        "/snapshot - Capture current image\n"
        "/toggle_motion - Toggle motion detection\n"
        "/alarm - Trigger alarm for 5 seconds"
    )

def send_status(update, context):
    """Send system status"""
    status = {
        "Motion Detection": "ON" if motion_enabled else "OFF",
        "Motion Events": motion_count,
        "Uptime": str(datetime.timedelta(seconds=int(time.time() - system_start_time))),
        "Camera": "Connected" if camera and camera.isOpened() else "Disconnected"
    }
    update.message.reply_text("\n".join(f"{k}: {v}" for k, v in status.items()))

def send_snapshot(update, context):
    """Capture and send current frame"""
    try:
        if camera:
            ret, frame = camera.read()
            if ret:
                _, buffer = cv2.imencode('.jpg', cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                update.message.reply_photo(photo=buffer.tobytes())
            else:
                update.message.reply_text("Failed to capture image")
        else:
            update.message.reply_text("Camera not available")
    except Exception as e:
        update.message.reply_text(f"Error: {str(e)}")

def toggle_motion_bot(update, context):
    global motion_enabled
    motion_enabled = not motion_enabled
    update.message.reply_text(f"Motion detection {'ENABLED' if motion_enabled else 'DISABLED'}")
    socketio.emit('motion_toggle', {'enabled': motion_enabled})

def trigger_alarm_bot(update, context):
    threading.Thread(target=trigger_alarm).start()
    update.message.reply_text("Alarm triggered for 5 seconds")

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
        if camera:
            ret, frame = camera.read()
            if ret:
                _, buffer = cv2.imencode('.jpg', cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                return Response(buffer.tobytes(), mimetype='image/jpeg')
        return "Camera error", 500
    except Exception as e:
        return str(e), 500

@app.route('/toggle_motion', methods=['POST'])
def toggle_motion():
    global motion_enabled
    motion_enabled = not motion_enabled
    socketio.emit('motion_toggle', {'enabled': motion_enabled})
    return jsonify({'status': 'success', 'motion_enabled': motion_enabled})

@app.route('/trigger_alarm', methods=['POST'])
def alarm_endpoint():
    threading.Thread(target=trigger_alarm).start()
    return jsonify({'status': 'success'})

# ===== Cleanup Handler =====
def cleanup():
    print("\nCleaning up resources...")
    try:
        if camera:
            camera.release()
        if video_writer:
            video_writer.release()
        if TELEGRAM_AVAILABLE and telegram_app:
            if TELEGRAM_NEW:
                telegram_app.stop()
            else:
                telegram_app.stop()
        if using_gpiozero:
            buzzer.off()
        else:
            import RPi.GPIO as GPIO
            GPIO.output(BUZZER_PIN, False)
            GPIO.cleanup()
    except Exception as e:
        print(f"Cleanup error: {e}")

# ===== Main Execution =====
if __name__ == '__main__':
    # Create default HTML interface if missing
    os.makedirs('templates', exist_ok=True)
    if not os.path.exists('templates/index.html'):
        with open('templates/index.html', 'w') as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Security Camera</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .video-container { background: #000; margin-bottom: 20px; }
        button { padding: 10px 15px; margin: 5px; font-size: 16px; }
        .status { margin: 20px 0; padding: 10px; background: #f5f5f5; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Security Camera</h1>
        <div class="video-container">
            <img src="/video_feed" width="640" height="480">
        </div>
        <div class="status">
            Motion Detection: <span id="motion-status">Active</span>
            | Events: <span id="motion-count">0</span>
        </div>
        <div>
            <button onclick="fetch('/toggle_motion', {method: 'POST'})">
                Toggle Motion
            </button>
            <button onclick="window.open('/snapshot')">
                Take Snapshot
            </button>
            <button onclick="fetch('/trigger_alarm', {method: 'POST'})">
                Test Alarm
            </button>
        </div>
    </div>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script>
        const socket = io();
        socket.on('motion_toggle', data => {
            document.getElementById('motion-status').textContent = 
                data.enabled ? 'Active' : 'Inactive';
        });
        socket.on('update_stats', data => {
            document.getElementById('motion-count').textContent = data.motion_count;
        });
    </script>
</body>
</html>""")

    # Start Telegram bot handlers if available
    if TELEGRAM_AVAILABLE and telegram_app:
        if TELEGRAM_NEW:
            telegram_app.add_handler(CommandHandler("start", start))
            telegram_app.add_handler(CommandHandler("status", send_status))
            telegram_app.add_handler(CommandHandler("snapshot", send_snapshot))
            telegram_app.add_handler(CommandHandler("toggle_motion", toggle_motion_bot))
            telegram_app.add_handler(CommandHandler("alarm", trigger_alarm_bot))
            telegram_thread = threading.Thread(target=telegram_app.run_polling)
            telegram_thread.daemon = True
            telegram_thread.start()
        else:
            dp = telegram_app.dispatcher
            dp.add_handler(CommandHandler("start", start))
            dp.add_handler(CommandHandler("status", send_status))
            dp.add_handler(CommandHandler("snapshot", send_snapshot))
            dp.add_handler(CommandHandler("toggle_motion", toggle_motion_bot))
            dp.add_handler(CommandHandler("alarm", trigger_alarm_bot))
            telegram_app.start_polling()

    # Start motion detection thread
    motion_thread = threading.Thread(target=motion_detection)
    motion_thread.daemon = True
    motion_thread.start()

    # Setup cleanup handlers
    signal.signal(signal.SIGINT, lambda s, f: [cleanup(), exit(0)])
    signal.signal(signal.SIGTERM, lambda s, f: [cleanup(), exit(0)])

    # Start Flask app
    print(f"\n=== System Ready ===")
    print(f"Web Interface: http://{os.popen('hostname -I').read().strip()}:5000")
    if TELEGRAM_AVAILABLE and bot:
        print(f"Telegram Bot: t.me/RaspSec01_bot")
    print("===================\n")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)