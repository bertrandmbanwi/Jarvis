#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="JARVIS"
BUNDLE_ID="com.jarvis.assistant"
OUTPUT_DIR="$ROOT/dist"
INSTALL_DIR=""
CREATE_DMG="true"
LINKED_HOME="$ROOT"

usage() {
  cat <<'EOF'
Usage: scripts/package_macos_app.sh [options]

Build a Finder-launchable macOS app bundle for JARVIS.

Options:
  --output DIR          Directory where JARVIS.app and optional DMG are written.
  --jarvis-home DIR     Checkout/runtime directory the app should launch.
  --install-user        Copy JARVIS.app to ~/Applications after building.
  --install-system      Copy JARVIS.app to /Applications after building.
  --no-dmg              Skip creating dist/JARVIS.dmg.
  -h, --help            Show this help.

The generated app is a lightweight launcher over a JARVIS checkout. This keeps
runtime data, git updates, .venv, node_modules, and model caches outside the app
bundle, which is the safest shape for a local assistant under active development.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --jarvis-home)
      LINKED_HOME="$(cd "$2" && pwd)"
      shift 2
      ;;
    --install-user)
      INSTALL_DIR="$HOME/Applications"
      shift
      ;;
    --install-system)
      INSTALL_DIR="/Applications"
      shift
      ;;
    --no-dmg)
      CREATE_DMG="false"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$LINKED_HOME/start.sh" ]]; then
  echo "JARVIS runtime not found at $LINKED_HOME; missing start.sh" >&2
  exit 1
fi

APP_DIR="$OUTPUT_DIR/${APP_NAME}.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

cat > "$CONTENTS_DIR/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>${BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>0.3.0</string>
    <key>CFBundleVersion</key>
    <string>0.3.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>JARVIS uses the microphone for local voice commands.</string>
    <key>NSSpeechRecognitionUsageDescription</key>
    <string>JARVIS can transcribe voice commands locally when voice mode is enabled.</string>
    <key>NSAppleEventsUsageDescription</key>
    <string>JARVIS can automate macOS apps when you ask it to perform local actions.</string>
</dict>
</plist>
EOF

printf "%s\n" "$LINKED_HOME" > "$RESOURCES_DIR/jarvis-home"

cat > "$MACOS_DIR/$APP_NAME" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

APP_CONTENTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESOURCE_DIR="$APP_CONTENTS/Resources"
JARVIS_HOME="$(cat "$RESOURCE_DIR/jarvis-home" 2>/dev/null || true)"

if [[ -z "$JARVIS_HOME" || ! -f "$JARVIS_HOME/start.sh" ]]; then
  /usr/bin/osascript -e 'display dialog "JARVIS cannot find its runtime checkout. Rebuild the app with scripts/package_macos_app.sh --jarvis-home /path/to/Jarvis." buttons {"OK"} default button "OK" with icon stop'
  exit 1
fi

cd "$JARVIS_HOME"

if [[ ! -d ".venv" || ! -d "jarvis/ui/jarvis-ui/node_modules" ]]; then
  button=$(/usr/bin/osascript -e 'button returned of (display dialog "JARVIS dependencies are not installed for this checkout. Install them now?" buttons {"Cancel", "Install"} default button "Install" with icon note)' || true)
  if [[ "$button" != "Install" ]]; then
    exit 0
  fi
  install_command=$(printf 'cd %q && bash scripts/install_macos.sh && ./start.sh full' "$JARVIS_HOME")
  install_command="${install_command//\\/\\\\}"
  install_command="${install_command//\"/\\\"}"
  /usr/bin/osascript \
    -e 'tell application "Terminal"' \
    -e 'activate' \
    -e "do script \"$install_command\"" \
    -e 'end tell'
  exit 0
fi

launch_command=$(printf 'cd %q && ./start.sh full' "$JARVIS_HOME")
launch_command="${launch_command//\\/\\\\}"
launch_command="${launch_command//\"/\\\"}"
/usr/bin/osascript \
  -e 'tell application "Terminal"' \
  -e 'activate' \
  -e "do script \"$launch_command\"" \
  -e 'end tell'
EOF
chmod +x "$MACOS_DIR/$APP_NAME"

ICON_SOURCE="$ROOT/jarvis/extensions/chrome/icons/icon-128.png"
if [[ -f "$ICON_SOURCE" && "$(uname -s)" == "Darwin" ]] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  ICONSET="$RESOURCES_DIR/JARVIS.iconset"
  mkdir -p "$ICONSET"
  sips -z 16 16 "$ICON_SOURCE" --out "$ICONSET/icon_16x16.png" >/dev/null
  sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
  sips -z 32 32 "$ICON_SOURCE" --out "$ICONSET/icon_32x32.png" >/dev/null
  sips -z 64 64 "$ICON_SOURCE" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
  sips -z 128 128 "$ICON_SOURCE" --out "$ICONSET/icon_128x128.png" >/dev/null
  sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
  sips -z 256 256 "$ICON_SOURCE" --out "$ICONSET/icon_256x256.png" >/dev/null
  sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
  sips -z 512 512 "$ICON_SOURCE" --out "$ICONSET/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "$ICON_SOURCE" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
  if iconutil -c icns "$ICONSET" -o "$RESOURCES_DIR/JARVIS.icns" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string JARVIS" "$CONTENTS_DIR/Info.plist" >/dev/null 2>&1 || true
  else
    echo "Warning: icon generation failed; continuing without a custom app icon." >&2
  fi
  rm -rf "$ICONSET"
fi

if [[ -n "$INSTALL_DIR" ]]; then
  mkdir -p "$INSTALL_DIR"
  rm -rf "$INSTALL_DIR/${APP_NAME}.app"
  cp -R "$APP_DIR" "$INSTALL_DIR/${APP_NAME}.app"
  echo "Installed $INSTALL_DIR/${APP_NAME}.app"
fi

if [[ "$CREATE_DMG" == "true" && "$(uname -s)" == "Darwin" ]] && command -v hdiutil >/dev/null 2>&1; then
  DMG_PATH="$OUTPUT_DIR/${APP_NAME}.dmg"
  rm -f "$DMG_PATH"
  hdiutil create -volname "$APP_NAME" -srcfolder "$APP_DIR" -ov -format UDZO "$DMG_PATH" >/dev/null
  echo "Created $DMG_PATH"
fi

echo "Created $APP_DIR"
