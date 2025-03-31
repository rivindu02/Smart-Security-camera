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
from telegram import Bot
from telegram.error import TelegramError

# Configuration
PIR_PIN = 17
BUZZER_PIN = 18
TELEGRAM_TOKEN = "7856984447:AAHLk7zu6mFjYK1_n3VUKoqwPxLfSPe-pJw"
TELEGRAM_CHAT_ID = "1162258333"
RESOLUTION = (640, 480)
FPS = 30
RECORD_DURATION = 10  # Seconds to record
COOLDOWN_TIME = 30    # Seconds between detections
OUTPUT_DIR = "recordings"
USB_CAMERA_INDEX = 0

# Initialize hardware
pir = MotionSensor(PIR_PIN)
buzzer = Buzzer(BUZZER_PIN)

# Initialize camera (we'll create a new one for each recording)
camera = None

# Initialize Telegram bot
try:
    bot = Bot(token=TELEGRAM_TOKEN)
    print("Telegram bot initialized successfully")
except TelegramError as e:
    print(f"Failed to initialize Telegram bot: {e}")
    bot = None

# Flask setup
app = Flask(__name__)
socketio = SocketIO(app)

# Global variables
motion_enabled = True
recording = False
motion_count = 0
system_start_time = time.time()

def get_camera():
    """Initialize and return a new camera instance"""
    cam = cv2.VideoCapture(USB_CAMERA_INDEX)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
    cam.set(cv2.CAP_PROP_FPS, FPS)
    return cam

def generate_frames():
    """Generate frames from a dedicated camera instance"""
    cam = get_camera()
    while True:
        ret, frame = cam.read()
        if not ret:
            break
            
        if recording:
            cv2.putText(frame, "RECORDING", (10, 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.putText(frame, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
        
        _, buffer = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
    cam.release()

def trigger_alarm(duration=1):
    buzzer.on()
    time.sleep(duration)
    buzzer.off()
    socketio.emit('alarm_triggered')

def record_video():
    global recording, motion_count
    
    recording = True
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{OUTPUT_DIR}/motion_{timestamp}.mp4"
    
    # Use a dedicated camera instance for recording
    record_cam = get_camera()
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, FPS, RESOLUTION)
    
    print(f"Starting recording to {filename}")
    start_time = time.time()
    
    try:
        while (time.time() - start_time) < RECORD_DURATION and motion_enabled:
            ret, frame = record_cam.read()
            if ret:
                out.write(frame)
            time.sleep(1/FPS)
    except Exception as e:
        print(f"Recording error: {e}")
    finally:
        out.release()
        record_cam.release()
        print(f"Finished recording: {filename}")
        
        # Send via Telegram if available
        if bot and os.path.exists(filename):
            try:
                with open(filename, 'rb') as video_file:
                    bot.send_video(
                        chat_id=TELEGRAM_CHAT_ID,
                        video=video_file,
                        caption=f"Motion detected at {timestamp}",
                        supports_streaming=True,
                        timeout=20
                    )
                print("Video sent successfully")
                os.remove(filename)
            except Exception as e:
                print(f"Failed to send video: {e}")
        
        recording = False
        motion_count += 1
        socketio.emit('motion_recorded', {'count': motion_count})

def motion_detection():
    while True:
        if pir.motion_detected and not recording and motion_enabled:
            print("Motion detected - triggering alarm and recording")
            threading.Thread(target=trigger_alarm).start()
            threading.Thread(target=record_video).start()
            time.sleep(COOLDOWN_TIME)
        time.sleep(0.1)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/test_alarm')
def test_alarm():
    threading.Thread(target=trigger_alarm).start()
    return jsonify({'status': 'success'})

@app.route('/test_recording')
def test_recording():
    if not recording:
        threading.Thread(target=record_video).start()
        return jsonify({'status': 'started'})
    return jsonify({'status': 'already_recording'})

if __name__ == '__main__':
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Create simple web interface
    if not os.path.exists('templates/index.html'):
        with open('templates/index.html', 'w') as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Security Camera</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; }
        #video { background: #000; margin: 0 auto; }
        button { padding: 10px 20px; margin: 10px; }
    </style>
</head>
<body>
    <h1>Security Camera</h1>
    <img id="video" src="/video_feed" width="640" height="480">
    <div>
        <button onclick="fetch('/test_alarm')">Test Alarm</button>
        <button onclick="fetch('/test_recording')">Test Recording</button>
    </div>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <script>
        const socket = io();
        socket.on('alarm_triggered', () => alert("Alarm sounded!"));
        socket.on('motion_recorded', (data) => alert(`Recorded ${data.count} motions`));
    </script>
</body>
</html>""")

    # Start motion detection thread
    threading.Thread(target=motion_detection, daemon=True).start()
    
    # Start web server
    print("Starting server at http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000)
