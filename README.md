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
| **Per-device delay compensation** | Adjust delay offset (0–500 ms) per device to sync wired and wireless outputs |
| **Mute All** | One-click global mute for all devices at once |
| **Live VU meters** | Stereo peak meters on the master bus and every output strip |
| **Application mixer** | Per-app volume and mute control for apps currently playing audio |
| **Hot-swap devices** | Enable / disable individual outputs mid-session without restarting |
| **Source selector** | Choose which audio device acts as the capture source (loopback) |
| **Low latency** | WASAPI loopback capture with ~21 ms latency at 48 kHz / 1024 block |
| **Audio profiles** | Save and load named presets (e.g., "Movie Night", "Work", "Party") with one click |
| **Profile import/export** | Share profiles between PCs via JSON file export and import |
| **Persistent settings** | Window size, device selections, volumes, and preferences are remembered across sessions |
| **System tray** | Minimise to tray with Start/Stop/Mute controls in the right-click menu |
| **Dark / Light theme** | Toggle between dark and light themes (Ctrl+T) |
| **Device search** | Filter the device list by name or API type |
| **Keyboard shortcuts** | Ctrl+R (Start/Stop), Ctrl+M (Mute All), Ctrl+↑/↓ (volume), Ctrl+S (save profile) |
| **Global hotkeys** | System-wide hotkeys work even when the app is minimised (Ctrl+Alt+R/M/↑/↓) |
| **Auto-start** | Option to automatically begin routing on launch with the last-used configuration |
| **Auto-start with Windows** | Optional Windows startup entry to launch the app at login |
| **Device notifications** | Automatic detection when devices connect or disconnect |
| **Notification sounds** | Audible feedback for routing start/stop, errors, and recording events |
| **Error recovery** | Graceful handling of device failures with automatic reconnection attempts |
| **Diagnostics log** | Built-in log panel showing real-time engine events and errors |
| **CPU monitoring** | Status bar shows callback duration and buffer underrun count |
| **10-band equalizer** | Master EQ with presets (Flat, Bass Boost, Treble Boost, Vocal, Rock, Electronic) |
| **Volume limiter** | Soft-clip peak limiter to prevent clipping distortion with configurable threshold |
| **Audio ducking** | Automatically lower volume when a priority app (e.g. Discord) is active |
| **Sample rate selector** | Choose between 44.1 kHz, 48 kHz, and 96 kHz sample rates |
| **Waveform visualizer** | Scrolling real-time waveform display of audio output |
| **Device groups / zones** | Save named device groups (e.g. "Office", "Streaming") for quick switching |
| **Device drag-and-drop** | Reorder device cards by dragging them into your preferred order |
| **Device health panel** | Detailed diagnostics showing per-device status, latency, errors, and performance |
| **Timed recording** | Record system audio with an optional duration timer (0 = unlimited) |
| **Compact mini mode** | Floating always-on-top mini window with VU meter, volume, and routing controls |
| **Multi-monitor support** | Remembers window position per monitor configuration |

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
| **scipy** | 1.7+ *(optional — enables 10-band equalizer DSP)* |

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

### Option C — Standalone executable

```bash
# Build with PyInstaller
pip install pyinstaller
pyinstaller build.spec

# Run the executable
dist/MultiOutputAudioConsole/MultiOutputAudioConsole.exe
```

---

## ⌨️ Keyboard Shortcuts

### In-app shortcuts

| Shortcut | Action |
|---|---|
| **Ctrl+R** | Start / Stop routing |
| **Ctrl+M** | Mute / Unmute all |
| **Ctrl+↑** | Master volume up (+5%) |
| **Ctrl+↓** | Master volume down (−5%) |
| **Ctrl+S** | Save current config as a profile |
| **Ctrl+T** | Toggle dark / light theme |

### Global hotkeys (work when minimised / in tray)

| Shortcut | Action |
|---|---|
| **Ctrl+Alt+R** | Toggle routing on/off |
| **Ctrl+Alt+M** | Toggle mute all |
| **Ctrl+Alt+↑** | Master volume up (+5%) |
| **Ctrl+Alt+↓** | Master volume down (−5%) |
| **Ctrl+Alt+P** | Toggle recording |

---

## 📖 How to Use

### 1. Select Output Devices

The **OUTPUT DEVICES** panel lists every audio device Windows knows about.
Tick the checkbox next to each device you want to receive audio.
Use the search bar to filter devices by name or API type.

### 2. Choose a Capture Source

Use the **Capture Source** dropdown in the toolbar to select which audio
output the app should "listen to" and re-broadcast.  
In most cases this is your current default device (speakers or headphones).

### 3. Start Routing

Click **▶ START ROUTING** (or press **Ctrl+R**).  
The selected output devices will all begin playing the same audio in sync.
The status indicator turns green and VU meters animate.

### 4. Adjust Volumes

- **Master Volume** — vertical slider on the left panel scales output on all devices proportionally.
- **Per-device sliders** — fine-tune each output independently.
- **Mute buttons** — silence any device instantly (🔊 → 🔇).
- **Delay sliders** — add delay (ms) to sync wired and wireless outputs.

### 5. Audio Profiles

Click **💾 Save** in the toolbar to save your current configuration as a
named profile. Select a profile from the dropdown to restore it instantly.

### 6. Application Mixer

The **APPLICATION MIXER** section shows every Windows audio session currently
active.  Use the sliders to lower the volume of one app (e.g. Chrome) while
keeping another louder (e.g. Spotify).

> **Note:** Routing specific apps to *different* output devices requires a
> virtual audio cable driver (e.g. VB-Audio Cable).  The application mixer
> here controls per-app volume on the *current* default device.

### 7. System Tray

When you close the window, the app minimises to the system tray. Double-click
the tray icon to restore the window. Right-click for quick Start/Stop/Mute
controls.

### 8. Stop Routing

Click **⏹ STOP** (or press **Ctrl+R**) to end all routing and release audio devices.

---

## ⚙️ Troubleshooting

### "Cannot start loopback capture"

1. Make sure the **Capture Source** device is set to your active audio output.
2. On older Windows builds, go to **Sound Settings → Recording** tab, right-click
   an empty area, enable *"Show Disabled Devices"*, then enable **Stereo Mix**.

### No audio on a Bluetooth device

Bluetooth devices sometimes need a few seconds to connect after being enabled.
If a device shows an error, click **⟳ Refresh**, re-enable the device, and
click **▶ START ROUTING** again. The app will also automatically attempt to
reconnect failed devices.

### High latency / audio glitches

- Reduce other CPU-intensive applications.
- Try disconnecting and reconnecting Bluetooth devices (they often negotiate
  a higher-latency profile when multiple codecs compete).
- Use the **delay slider** on each device card to compensate for different
  device latencies.
- Ensure your system is not in a power-saving mode.
- Check the **Diagnostics Log** panel for error messages.

---

## 🧪 Running Tests

```bash
python -m pytest tests/ -v
```

Or with unittest:

```bash
python -m unittest discover tests -v
```

---

## 🗂️ Project Structure

```
multi-out-audio/
├── main.py                  # Entry point
├── requirements.txt         # Python dependencies
├── run.bat                  # Windows one-click launcher
├── build.spec               # PyInstaller build spec
├── audio_engine.py          # WASAPI loopback capture + multi-output fan-out + EQ/limiter
├── device_manager.py        # Windows audio session management (pycaw)
├── settings_manager.py      # Persistent settings (QSettings)
├── profile_manager.py       # Audio profile / preset management + import/export
├── equalizer.py             # 10-band parametric EQ with presets (scipy)
├── hotkey_manager.py        # System-wide global hotkeys (Win32 API)
├── autostart.py             # Windows startup registry management
├── ui/
│   ├── main_window.py       # Main PyQt5 window with tabbed panels
│   ├── device_card.py       # Per-output-device control strip (drag-and-drop)
│   ├── app_strip.py         # Per-application volume strip
│   ├── vu_meter.py          # Animated stereo VU meter widget
│   ├── waveform_widget.py   # Scrolling real-time waveform visualizer
│   ├── mini_window.py       # Compact floating mini-mode window
│   └── styles.py            # Dark and light QSS themes
└── tests/
    ├── test_audio_engine.py      # Audio router unit tests
    ├── test_settings_manager.py  # Settings persistence tests
    ├── test_profile_manager.py   # Profile management tests
    ├── test_equalizer.py         # Equalizer unit tests
    └── test_hotkey_manager.py    # Hotkey manager tests
```

---

## 📄 License

See [LICENSE](LICENSE).
