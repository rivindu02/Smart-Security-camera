# 🛡️ Smart Security Camera (PiGuard)

**Raspberry Pi-based intelligent security camera system with motion detection, night vision support, and Telegram integration**

![Demo](demo.gif)

## 📋 Overview

PiGuard is a comprehensive Python-based security camera solution designed for Raspberry Pi. The system automatically detects motion using a PIR sensor, captures video footage with a night vision-capable camera, triggers an alarm, and sends recorded videos directly to users via Telegram for instant notifications.

## ✨ Key Features

- 🎥 **Real-time Video Streaming** - Live video feed accessible via web interface
- 🚨 **Motion Detection** - PIR sensor-based motion detection with configurable sensitivity
- 📹 **Automatic Recording** - Records 3-minute videos when motion is detected
- 🌙 **Night Vision Support** - Compatible with infrared night vision cameras
- 📱 **Telegram Integration** - Instant video alerts sent to your phone
- 🔔 **Audio Alarm** - Buzzer activation on motion detection
- 🌐 **Web Interface** - Modern, responsive web dashboard for monitoring
- ⚡ **Real-time Notifications** - WebSocket-based instant updates
- 🎛️ **Remote Control** - Toggle motion detection, trigger alarms, take snapshots
- 💾 **Local Storage** - Video recordings stored in the `recordings/` directory

## 🔧 Hardware Setup

### Required Components
- **Raspberry Pi** (4B recommended) with Raspberry Pi OS
- **Camera Module** - Raspberry Pi Camera Module V2/V3 with night vision support OR USB camera
- **PIR Motion Sensor** - HC-SR501 or similar
- **Buzzer** - Active buzzer for alarm notifications
- **Jumper Wires** and **Breadboard**

### Circuit Connections

#### PIR Sensor
- **VCC** → Raspberry Pi **5V** (Pin 2)
- **GND** → Raspberry Pi **GND** (Pin 6)
- **OUT** → Raspberry Pi **GPIO 17** (Pin 11)

#### Buzzer
- **Positive** → Raspberry Pi **GPIO 18** (Pin 12)
- **Negative** → Raspberry Pi **GND** (Pin 14)

#### Camera
- **Raspberry Pi Camera**: Connect via CSI cable to camera port
- **USB Camera**: Connect to any USB port

```
     Raspberry Pi                PIR Sensor
    ┌─────────────┐              ┌─────────┐
    │  5V    GND  │  ────────────┤ VCC GND │
    │ Pin2   Pin6 │              │         │
    │             │              │   OUT   │
    │ GPIO17      │  ────────────┤         │
    │ Pin11       │              └─────────┘
    │             │
    │ GPIO18      │              ┌─────────┐
    │ Pin12       │  ────────────┤ Buzzer  │
    │  GND        │  ────────────┤   +/-   │
    │ Pin14       │              └─────────┘
    └─────────────┘
```

## 🚀 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/rivindu02/Smart-Security-camera.git
cd Smart-Security-camera
```

### 2. Install Dependencies
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python packages
pip install flask flask-socketio opencv-python-headless picamera2 gpiozero python-telegram-bot numpy

# Enable camera interface (for Pi Camera)
sudo raspi-config
# Navigate to Interface Options > Camera > Enable
```

### 3. Configure Telegram Bot

1. **Create a Telegram Bot**:
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Send `/newbot` and follow instructions
   - Save the bot token

2. **Get Your Chat ID**:
   - Message your bot
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find your chat ID in the response

3. **Update Configuration**:
   ```python
   # In security_camera.py, update these lines:
   TELEGRAM_TOKEN = "your_bot_token_here"
   TELEGRAM_CHAT_ID = "your_chat_id_here"
   ```

### 4. Run the Application

#### For Raspberry Pi Camera:
```bash
python security_camera.py
```

#### For USB Camera:
```bash
python usb.py
```

#### For Testing Hardware:
```bash
python hardwaretest.py
```

## 💻 Usage

### Web Interface
Access the web dashboard at `http://<raspberry_pi_ip>:5000`

**Features:**
- 📺 Live video stream
- 📊 Real-time statistics (motion events, uptime)
- 🎛️ Motion detection toggle
- 📸 Manual snapshot capture
- 🔔 Test alarm functionality
- 📱 Recent alerts log

### Telegram Commands
Your Telegram bot supports these commands:
- `/start` - Initialize bot and show available commands
- `/status` - Get system status and statistics
- `/snapshot` - Capture and receive current image
- `/toggle_motion` - Enable/disable motion detection
- `/alarm` - Trigger alarm for testing

### API Endpoints
- `GET /` - Web interface
- `GET /video_feed` - Live video stream
- `GET /snapshot` - Capture image
- `POST /toggle_motion` - Toggle motion detection
- `POST /trigger_alarm` - Activate buzzer

## 📁 Project Structure

```
Smart-Security-camera/
├── security_camera.py      # Main script for Pi Camera
├── usb.py                  # USB camera version
├── new.py                  # Enhanced version with additional features
├── hardwaretest.py         # Hardware testing script
├── debug.py               # Debugging utilities
├── debug2.py              # Advanced debugging
├── debug3.py              # Latest debugging version
├── templates/
│   └── index.html         # Modern web interface
├── recordings/            # Video storage directory
│   ├── motion_*.mp4       # Recorded motion videos
│   └── ...
├── demo.gif               # Project demonstration
└── README.md              # This file
```

## ⚙️ Configuration Options

### Camera Settings
```python
RESOLUTION = (640, 480)    # Video resolution
FPS = 30                   # Frames per second
```

### Motion Detection
```python
PIR_PIN = 17              # PIR sensor GPIO pin
RECORD_DURATION = 180     # Recording length (seconds)
COOLDOWN_TIME = 300       # Delay between detections (seconds)
```

### Alert System
```python
BUZZER_PIN = 18           # Buzzer GPIO pin
TELEGRAM_TOKEN = "..."    # Bot token
TELEGRAM_CHAT_ID = "..."  # Your chat ID
```

## 🔧 Troubleshooting

### Common Issues

**Camera not working:**
```bash
# Enable camera interface
sudo raspi-config

# Check camera connection
vcgencmd get_camera

# For USB cameras, list devices
lsusb
```

**GPIO Permission errors:**
```bash
# Add user to gpio group
sudo usermod -a -G gpio $USER

# Reboot after adding to group
sudo reboot
```

**Telegram bot not responding:**
- Verify bot token and chat ID
- Check internet connection
- Ensure bot is started with `/start` command

**Module import errors:**
```bash
# Install missing packages
pip install -r requirements.txt

# For system-wide installation
sudo pip install <package_name>
```

## 🔮 Future Enhancements

-  **Face Recognition** - Identify known vs unknown individuals
- **Cloud Storage** - Upload recordings to Google Drive/Dropbox
- **Mobile App** - Dedicated smartphone application
- **AI Object Detection** - Distinguish between humans, animals, vehicles
-  **Multi-Camera Support** - Monitor multiple locations
- **Time-lapse Recording** - Create time-lapse videos
- **Motion Zones** - Define specific areas for detection
- **Smart Notifications** - Reduce false positives with AI

## 🛠️ Development

### Testing Components
```bash
# Test PIR sensor and buzzer
python hardwaretest.py

# Debug camera functionality
python debug.py

# Test specific features
python debug2.py  # Advanced testing
python debug3.py  # Latest testing version
```

### Code Structure
- **Hardware Layer**: GPIO control, camera interface
- **Detection Layer**: Motion sensing, alarm triggering
- **Recording Layer**: Video capture, file management
- **Communication Layer**: Telegram integration, web interface
- **Web Layer**: Flask server, SocketIO real-time updates

## 📄 License

This project is open source. Feel free to use, modify, and distribute according to your needs.

## 👨‍💻 Author

**Rivindu** - [GitHub Profile](https://github.com/rivindu02)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## ⭐ Show Your Support

Give a ⭐️ if this project helped you!

## 📞 Support

For support, email [your-email] or open an issue in the GitHub repository.

---
