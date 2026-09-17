# SapthaEvent Mobile Engineering Guide

## 1. Mobile-First Philosophy
SapthaEvent is architected from the viewport up to deliver 60 FPS fluid touch interactions across mobile browsers, tablets, and native apps:
- **Fluid Layouts**: Pure CSS modern responsive grids, fluid typography using `clamp()`, and touch targets minimum 48px × 48px.
- **Glassmorphic UI**: Ultra-modern frosted acrylic headers, translucent bottom navigation bars, and micro-haptic visual feedback.
- **Gesture Controls**: Swipe-to-dismiss modals, pull-to-refresh feeds, and bottom-sheet drawers.

---

## 2. Capacitor Cross-Platform Integration

The repository integrates `@capacitor/core` and `@capacitor/cli` (`capacitor.config.json`):
```json
{
  "appId": "in.edu.snpsu.sapthaevent",
  "appName": "SapthaEvent",
  "webDir": "static",
  "bundledWebRuntime": false,
  "server": {
    "url": "https://events.snpsu.edu.in",
    "cleartext": false
  }
}
```

### Supported Native Capabilities
1. **Camera Stream & Scanner**: Direct hardware access to rear camera via `@capacitor/camera` and `html5-qrcode` fallback for high-speed ticket scanning.
2. **Local Push Notifications**: Scheduled alarms for registered sessions, milestone deadlines, and stage transitions.
3. **Biometric Authentication**: Fingerprint / Face ID unlocking for judging panels and coordinator scan HUDs.
4. **Haptics**: Instant vibration cues on valid (double light tap) and invalid (heavy error pulse) ticket scans.

---

## 3. High-Speed Coordinator Scan HUD

The Coordinator HUD (`/coordinator/scan-hud/<event_id>`) transforms any smartphone into a gate pass scanner:
- Continuous autofocus video feed.
- Audio tone synthesis (Web Audio API) for instant sensory feedback without external sound files.
- Sub-50ms token decoding.
- Dynamic statistics drawer: Live counts of Checked-In vs Remaining attendees with real-time progress gauge.

---

## 4. Building Native Packages

### Android APK / AAB
```bash
# Sync web build to Android project
npx cap sync android

# Open Android Studio
npx cap open android
```

### iOS App
```bash
# Sync web build to iOS project
npx cap sync ios

# Open Xcode workspace
npx cap open ios
```
