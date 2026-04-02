#!/bin/bash
set -euo pipefail

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if swiftc is available
if ! command -v swiftc &> /dev/null; then
    echo -e "${RED}Error: swiftc not found. Make sure Xcode Command Line Tools are installed.${NC}"
    echo "Install with: xcode-select --install"
    exit 1
fi

echo -e "${BLUE}JARVIS Desktop Overlay Build${NC}"
echo -e "${BLUE}=============================${NC}"

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"
APP_NAME="JarvisOverlay"
APP_BUNDLE="${BUILD_DIR}/${APP_NAME}.app"
MACOS_DIR="${APP_BUNDLE}/Contents/MacOS"
RESOURCES_DIR="${APP_BUNDLE}/Contents"

# Clean previous build
if [ -d "$BUILD_DIR" ]; then
    echo -e "${YELLOW}Cleaning previous build...${NC}"
    rm -rf "$BUILD_DIR"
fi

# Create app bundle structure
echo -e "${YELLOW}Creating app bundle structure...${NC}"
mkdir -p "$MACOS_DIR"

# Compile Swift file
echo -e "${YELLOW}Compiling Swift code...${NC}"
swiftc -framework Cocoa -framework WebKit -O \
    -o "${MACOS_DIR}/${APP_NAME}" \
    "${SCRIPT_DIR}/JarvisOverlay.swift"

if [ ! -f "${MACOS_DIR}/${APP_NAME}" ]; then
    echo -e "${RED}Compilation failed!${NC}"
    exit 1
fi

echo -e "${GREEN}Compilation successful${NC}"

# Create Info.plist
echo -e "${YELLOW}Creating Info.plist...${NC}"
cat > "${RESOURCES_DIR}/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>JarvisOverlay</string>
    <key>CFBundleIdentifier</key>
    <string>com.jarvis.desktop-overlay</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>JARVIS Overlay</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSRequiresIPhoneOS</key>
    <false/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsArbitraryLoadsInWebContent</key>
        <true/>
    </dict>
</dict>
</plist>
EOF

echo -e "${GREEN}Info.plist created${NC}"

# Make executable
chmod +x "${MACOS_DIR}/${APP_NAME}"

# Print success message
echo -e "${GREEN}=============================${NC}"
echo -e "${GREEN}Build completed successfully!${NC}"
echo -e "${GREEN}=============================${NC}"
echo ""
echo -e "${BLUE}Usage:${NC}"
echo -e "  ${YELLOW}open ${APP_BUNDLE}${NC}"
echo ""
echo -e "${BLUE}To auto-start on login:${NC}"
echo "  1. Open System Settings"
echo "  2. Go to General > Login Items"
echo "  3. Click the '+' button"
echo "  4. Navigate to: ${APP_BUNDLE}"
echo "  5. Click 'Add'"
echo ""
echo -e "${BLUE}To manage login items via command line:${NC}"
echo -e "  ${YELLOW}open ~/.login-items.plist${NC}"
echo ""
