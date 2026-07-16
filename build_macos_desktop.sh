#!/usr/bin/env bash
# ==============================================================================
# Agentic OS Platform v10.0 — Automated macOS Desktop (.dmg / .app) Build Script
# Created by Joshua Strickland and Strick Tech
# Supports:
#   --bundle-python : Downloads & bundles a standalone Python runtime inside .app
#   --sign          : Uses $APPLE_SIGNING_IDENTITY to sign the application bundle
#   --notarize      : Uses $APPLE_ID, $APPLE_PASSWORD, $APPLE_TEAM_ID to notarize
# ==============================================================================
set -e

echo "🍏 ====================================================================="
echo "🍏  Agentic OS Platform v10.0 — macOS Native Application Builder"
echo "🍏  Created by Joshua Strickland & Strick Tech"
echo "🍏 ====================================================================="
echo ""

BUNDLE_PYTHON=0
SIGN_APP=0
NOTARIZE_APP=0

for arg in "$@"; do
  case $arg in
    --bundle-python) BUNDLE_PYTHON=1 ;;
    --sign) SIGN_APP=1 ;;
    --notarize) NOTARIZE_APP=1 ;;
  esac
done

if [ "$BUNDLE_PYTHON" -eq 1 ] || [ "$BUNDLE_PYTHON_ENV" = "1" ]; then
  BUNDLE_PYTHON=1
fi

# 1. Verify macOS Host
if [[ "$OSTYPE" != "darwin"* ]]; then
  echo "⚠️  Warning: This script is optimized for macOS (MacBook Pro / Apple Silicon / Intel)."
  echo "    Running on $OSTYPE — executing cross-platform build preparation..."
fi

# 2. Check Python 3.10+
if ! command -v python3 &> /dev/null; then
  echo "❌ Error: python3 could not be found. Please install Python 3.10+ via Homebrew or python.org."
  exit 1
fi
PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✅ Python $PYTHON_VER detected."

# 3. Check Rust & Cargo
if ! command -v cargo &> /dev/null; then
  if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
  else
    echo "⚠️  Cargo not found in PATH. Installing Rust & Cargo via rustup..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
  fi
fi
CARGO_VER=$(cargo --version)
echo "✅ Rust $CARGO_VER detected."

# 4. Install Python Backend Dependencies into Host/Dev Environment
echo "📦 Installing required Python dependencies into developer environment..."
python3 -m pip install --upgrade pip --quiet
python3 -m pip install -r requirements.txt --quiet
echo "✅ Python backend dependencies verified."

# 5. Optional: Standalone Embedded Python Runtime Bundling (python-build-standalone)
if [ "$BUNDLE_PYTHON" -eq 1 ]; then
  echo ""
  echo "🌟 [--bundle-python active] Preparing standalone embedded Python runtime..."
  ARCH=$(uname -m)
  if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
    PYTHON_ARCH="aarch64"
  else
    PYTHON_ARCH="x86_64"
  fi
  PYTHON_DIST="cpython-3.12.7+20241016-${PYTHON_ARCH}-apple-darwin-install_only.tar.gz"
  PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20241016/${PYTHON_DIST}"
  
  if [ ! -f "src-tauri/python_embedded/bin/python3" ]; then
    echo "📥 Downloading official python-build-standalone runtime (${PYTHON_ARCH})..."
    rm -rf src-tauri/python_embedded
    mkdir -p src-tauri/python_embedded
    curl -L --fail --retry 3 -o "/tmp/${PYTHON_DIST}" "$PYTHON_URL"
    tar -xzf "/tmp/${PYTHON_DIST}" -C src-tauri/python_embedded --strip-components=1
    rm -f "/tmp/${PYTHON_DIST}"
  fi
  
  if [ ! -f "src-tauri/python_embedded/bin/python3" ]; then
    echo "❌ Error: Embedded Python binary could not be found after extraction."
    exit 1
  fi
  
  EMBEDDED_PYTHON_VER=$(src-tauri/python_embedded/bin/python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  echo "✅ Embedded standalone Python $EMBEDDED_PYTHON_VER verified."
  echo "📦 Installing Agentic OS requirements directly into embedded runtime..."
  src-tauri/python_embedded/bin/python3 -m pip install --upgrade pip --quiet
  src-tauri/python_embedded/bin/python3 -m pip install -r requirements.txt --quiet
  echo "✅ Embedded standalone Python runtime bundled into src-tauri/python_embedded!"
fi

# 6. Check Tauri CLI
if ! command -v cargo-tauri &> /dev/null; then
  echo "📦 Installing Tauri CLI (cargo-tauri v2.x)..."
  cargo install tauri-cli --version "^2.0.0" --locked --quiet
fi
TAURI_VER=$(cargo tauri --version 2>/dev/null || echo "v2.0+")
echo "✅ Tauri CLI $TAURI_VER detected."

# 7. Build macOS Desktop Application (.dmg & .app bundle)
echo ""
echo "🚀 Launching native macOS desktop build..."
cd src-tauri

ARCH=$(uname -m)
BUILD_FLAGS=()

if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
  echo "🌟 Apple Silicon (M1/M2/M3/M4) detected. Compiling native aarch64 target..."
  if rustup target list 2>/dev/null | grep -q "aarch64-apple-darwin (installed)"; then
    BUILD_FLAGS+=("--target" "aarch64-apple-darwin")
  fi
else
  echo "🌟 Intel / Standard architecture ($ARCH) detected. Compiling native x86_64 target..."
  if rustup target list 2>/dev/null | grep -q "x86_64-apple-darwin (installed)"; then
    BUILD_FLAGS+=("--target" "x86_64-apple-darwin")
  fi
fi

# Apply Apple Code Signing Configuration if requested
if [ "$SIGN_APP" -eq 1 ] && [ -n "$APPLE_SIGNING_IDENTITY" ]; then
  echo "✍️  Signing identity provided: $APPLE_SIGNING_IDENTITY"
  cargo tauri build "${BUILD_FLAGS[@]}" --config '{"bundle": {"macOS": {"signingIdentity": "'"$APPLE_SIGNING_IDENTITY"'"}}}'
else
  cargo tauri build "${BUILD_FLAGS[@]}"
fi

cd ..

# 8. Optional: Apple Notarization
if [ "$NOTARIZE_APP" -eq 1 ] && [ -n "$APPLE_ID" ] && [ -n "$APPLE_PASSWORD" ] && [ -n "$APPLE_TEAM_ID" ]; then
  echo ""
  echo "🛡️  Submitting .dmg installer to Apple notarytool for verification..."
  DMG_PATH=$(find src-tauri/target -name "*.dmg" 2>/dev/null | head -n 1)
  if [ -n "$DMG_PATH" ]; then
    xcrun notarytool submit "$DMG_PATH" --apple-id "$APPLE_ID" --password "$APPLE_PASSWORD" --team-id "$APPLE_TEAM_ID" --wait
    xcrun stapler staple "$DMG_PATH"
    echo "✅ Notarization complete and ticket stapled to .dmg!"
  fi
fi

DMG_FOUND=$(find src-tauri/target -name "*.dmg" 2>/dev/null | head -n 1)
APP_FOUND=$(find src-tauri/target -name "*.app" 2>/dev/null | head -n 1)

echo ""
echo "🎉 ====================================================================="
echo "🎉  Agentic OS Platform v10.0 macOS Desktop App Built Successfully!"
if [ -n "$DMG_FOUND" ]; then
  echo "🎉  👉 DMG Installer : $DMG_FOUND"
fi
if [ -n "$APP_FOUND" ]; then
  echo "🎉  👉 App Bundle    : $APP_FOUND"
fi
echo "🎉 ====================================================================="
