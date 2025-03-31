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
TELEGRAM_TOKEN = "7856984447:AAHLk7zu6mFjYK1_n3VUKoqwPxLfSPe-pJw"  # Your bot token
TELEGRAM_CHAT_ID = "1162258333"  # Your chat ID
RESOLUTION = (640, 480)
FPS = 30
RECORD_DURATION = 10  # Seconds to record after motion
COOLDOWN_TIME = 30    # Seconds between detections
OUTPUT_DIR = "recordings"
USB_CAMERA_INDEX = 0

# Initialize hardware
pir = MotionSensor(PIR_PIN)
buzzer = Buzzer(BUZZER_PIN)
camera = cv2.VideoCapture(USB_CAMERA_INDEX)

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
video_writer = None

def generate_frames():
    while True:
        ret, frame = camera.read()
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

def trigger_alarm(duration=1):
    buzzer.on()
    time.sleep(duration)
    buzzer.off()
    socketio.emit('alarm_triggered')

def record_video():
    global recording, motion_count, video_writer
    recording = True
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{OUTPUT_DIR}/motion_{timestamp}.mp4"  # Using MP4 for Telegram
    
    # Use libx264 codec which Telegram prefers
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    video_writer = cv2.VideoWriter(filename, fourcc, FPS, RESOLUTION)
    
    start_time = time.time()
    while (time.time() - start_time) < RECORD_DURATION and motion_enabled:
        ret, frame = camera.read()
        if ret:
            video_writer.write(frame)
        time.sleep(1/FPS)
    
    video_writer.release()
    motion_count += 1
    
    # Send video via Telegram if bot is available
    if bot and os.path.exists(filename):
        try:
            with open(filename, 'rb') as video_file:
                bot.send_video(
                    chat_id=TELEGRAM_CHAT_ID,
                    video=video_file,
                    caption=f"Motion detected at {timestamp}",
                    supports_streaming=True
                )
            os.remove(filename)  # Clean up after sending
        except Exception as e:
            print(f"Failed to send video via Telegram: {e}")
    
    recording = False
    video_writer = None
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
