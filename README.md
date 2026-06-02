# 🔊 Multi-Output Audio Console

A Windows desktop application that lets you simultaneously route your PC's audio
to **any number of output devices** — speakers, Bluetooth headphones, HDMI, USB
audio, Wi-Fi speakers, and more — all in sync, with full independent volume
control per device.

![Dark audio console UI with master VU meter, device list, and app mixer](docs/screenshot.png)
*(Screenshot placeholder — run the app to see it live)*

---

## ✨ Features

| Feature | Details |
|---|---|
| **Multi-output routing** | Route system audio to 2, 3, 4, 5, 6 … as many devices as you like, simultaneously |
| **All connection types** | Works with Bluetooth, 3.5 mm jack, HDMI, DisplayPort, USB audio, Wi-Fi speakers — any device Windows sees |
| **Master volume control** | One slider controls overall output level across every active device |
| **Per-device volume** | Individual sliders for fine-tuned balance between each output |
| **Per-device mute** | Instantly silence any individual output without stopping routing |
| **Mute All** | One-click global mute for all devices at once |
| **Live VU meters** | Stereo peak meters on the master bus and every output strip |
| **Application mixer** | Per-app volume and mute control for apps currently playing audio |
| **Hot-swap devices** | Enable / disable individual outputs mid-session without restarting |
| **Source selector** | Choose which audio device acts as the capture source (loopback) |
| **Low latency** | WASAPI loopback capture with ~21 ms latency at 48 kHz / 1024 block |

---

## 🖥️ Requirements

| Requirement | Version |
|---|---|
| **Windows** | 10 / 11 (WASAPI loopback) |
| **Python** | 3.8 or newer |
| **PyQt5** | 5.15+ |
| **sounddevice** | 0.4.6+ |
| **numpy** | 1.21+ |
| **pycaw** | ≥ 20181226 *(optional — enables app mixer)* |
| **comtypes** | 1.1.14+ *(required by pycaw)* |
| **psutil** | 5.8+ *(optional — used by pycaw for process names)* |

---

## 🚀 Quick Start

### Option A — Double-click (easiest)

```
run.bat
```

The launcher automatically installs missing Python packages and starts the app.

### Option B — Command line

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
python main.py
```

---

## 📖 How to Use

### 1. Select Output Devices

The **OUTPUT DEVICES** panel lists every audio device Windows knows about.
Tick the checkbox next to each device you want to receive audio.

### 2. Choose a Capture Source

Use the **Capture Source** dropdown in the toolbar to select which audio
output the app should "listen to" and re-broadcast.  
In most cases this is your current default device (speakers or headphones).

### 3. Start Routing

Click **▶ START ROUTING**.  
The selected output devices will all begin playing the same audio in sync.
The status indicator turns green and VU meters animate.

### 4. Adjust Volumes

- **Master Volume** — vertical slider on the left panel scales output on all devices proportionally.
- **Per-device sliders** — fine-tune each output independently.
- **Mute buttons** — silence any device instantly (🔊 → 🔇).

### 5. Application Mixer

The **APPLICATION MIXER** section shows every Windows audio session currently
active.  Use the sliders to lower the volume of one app (e.g. Chrome) while
keeping another louder (e.g. Spotify).

> **Note:** Routing specific apps to *different* output devices requires a
> virtual audio cable driver (e.g. VB-Audio Cable).  The application mixer
> here controls per-app volume on the *current* default device.

### 6. Stop Routing

Click **⏹ STOP** to end all routing and release audio devices.

---

## ⚙️ Troubleshooting

### "Cannot start loopback capture"

1. Make sure the **Capture Source** device is set to your active audio output.
2. On older Windows builds, go to **Sound Settings → Recording** tab, right-click
   an empty area, enable *"Show Disabled Devices"*, then enable **Stereo Mix**.

### No audio on a Bluetooth device

Bluetooth devices sometimes need a few seconds to connect after being enabled.
If a device shows an error, click **⟳ Refresh**, re-enable the device, and
click **▶ START ROUTING** again.

### High latency / audio glitches

- Reduce other CPU-intensive applications.
- Try disconnecting and reconnecting Bluetooth devices (they often negotiate
  a higher-latency profile when multiple codecs compete).
- Ensure your system is not in a power-saving mode.

---

## 🗂️ Project Structure

```
multi-out-audio/
├── main.py              # Entry point
├── requirements.txt     # Python dependencies
├── run.bat              # Windows one-click launcher
├── audio_engine.py      # WASAPI loopback capture + multi-output fan-out
├── device_manager.py    # Windows audio session management (pycaw)
└── ui/
    ├── main_window.py   # Main PyQt5 window
    ├── device_card.py   # Per-output-device control strip
    ├── app_strip.py     # Per-application volume strip
    ├── vu_meter.py      # Animated stereo VU meter widget
    └── styles.py        # Dark QSS theme
```

---

## 📄 License

See [LICENSE](LICENSE).
