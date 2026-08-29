#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  Agentic OS — Tauri Desktop Build Pipeline
#  Compiles and packages the desktop app for macOS, Windows, Linux
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "╔══════════════════════════════════════════════════╗"
echo "║   Agentic OS — Tauri Desktop Build Pipeline     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. Check prerequisites ─────────────────────────────────────────────────────
check() {
  if ! command -v "$1" &>/dev/null; then
    echo "❌ $1 not found. $2"
    exit 1
  fi
  echo "✅ $1 found: $(command -v $1)"
}

check "rustc"   "Install Rust: https://rustup.rs"
check "cargo"   "Install Rust: https://rustup.rs"
check "python3" "Install Python 3: https://python.org"
check "node"    "Install Node.js (optional but recommended): https://nodejs.org"

RUST_VERSION=$(rustc --version)
echo "   Rust: $RUST_VERSION"

# ── 2. Install tauri-cli ──────────────────────────────────────────────────────
if ! cargo tauri --version &>/dev/null 2>&1; then
  echo ""
  echo "📦 Installing tauri-cli…"
  cargo install tauri-cli --version "^2"
fi
echo "✅ tauri-cli: $(cargo tauri --version)"

# ── 3. Install Python dependencies ───────────────────────────────────────────
echo ""
echo "📦 Installing Python dependencies…"
python3 -m pip install -r requirements.txt -q

# ── 4. Verify backend starts correctly ───────────────────────────────────────
echo ""
echo "🔍 Verifying backend syntax…"
python3 -c "
import sys; sys.path.insert(0, '.')
try:
    import backend.app
    print('✅ Backend imports OK')
except Exception as e:
    print(f'❌ Backend error: {e}')
    sys.exit(1)
"

# ── 5. Generate Tauri icons ───────────────────────────────────────────────────
echo ""
echo "🎨 Checking Tauri icons…"
ICONS_DIR="$ROOT/src-tauri/icons"
mkdir -p "$ICONS_DIR"

# Generate a placeholder icon if none exist
if [ ! -f "$ICONS_DIR/icon.png" ]; then
  echo "   Generating placeholder icon…"
  python3 -c "
import os
try:
    from PIL import Image, ImageDraw, ImageFont
    sizes = [(32,32),(128,128),(256,256)]
    for w,h in sizes:
        img = Image.new('RGBA', (w,h), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        # Background circle
        draw.ellipse([4,4,w-4,h-4], fill=(91,138,248,255))
        # Center dot
        cx, cy = w//2, h//2
        r = w//6
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(255,255,255,220))
        img.save(f'src-tauri/icons/{w}x{h}.png')
    # Copy main icon
    img = Image.open('src-tauri/icons/256x256.png')
    img.save('src-tauri/icons/icon.png')
    img.save('src-tauri/icons/128x128@2x.png')
    print('✅ Icons generated')
except ImportError:
    # Create minimal valid PNG (1x1 transparent)
    import struct, zlib
    def create_png(w, h, color=(91,138,248,255)):
        def chunk(name, data):
            c = zlib.crc32(name + data) & 0xffffffff
            return struct.pack('>I', len(data)) + name + data + struct.pack('>I', c)
        ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
        raw  = b''.join(b'\x00' + bytes([color[0],color[1],color[2]]*w) for _ in range(h))
        idat = zlib.compress(raw)
        return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')
    
    for size in ['32x32','128x128','256x256']:
        w,h = map(int, size.split('x'))
        open(f'src-tauri/icons/{size}.png','wb').write(create_png(w,h))
    import shutil
    shutil.copy('src-tauri/icons/256x256.png', 'src-tauri/icons/icon.png')
    shutil.copy('src-tauri/icons/256x256.png', 'src-tauri/icons/128x128@2x.png')
    print('✅ Basic icons created')
"
fi

# Create .icns stub for macOS (required by Tauri)
if [ ! -f "$ICONS_DIR/icon.icns" ] && command -v iconutil &>/dev/null; then
  echo "   Generating .icns for macOS…"
  ICONSET="$ICONS_DIR/icon.iconset"
  mkdir -p "$ICONSET"
  for size in 16 32 64 128 256 512; do
    cp "$ICONS_DIR/icon.png" "$ICONSET/icon_${size}x${size}.png" 2>/dev/null || true
    cp "$ICONS_DIR/icon.png" "$ICONSET/icon_${size}x${size}@2x.png" 2>/dev/null || true
  done
  iconutil -c icns "$ICONSET" -o "$ICONS_DIR/icon.icns" 2>/dev/null || true
fi

# Create .ico stub for Windows
if [ ! -f "$ICONS_DIR/icon.ico" ]; then
  python3 -c "
try:
    from PIL import Image
    img = Image.open('src-tauri/icons/icon.png').resize((64,64))
    img.save('src-tauri/icons/icon.ico', format='ICO')
    print('   icon.ico created')
except Exception:
    import shutil
    shutil.copy('src-tauri/icons/icon.png','src-tauri/icons/icon.ico')
    print('   icon.ico copied (stub)')
" 2>/dev/null || true
fi

echo "✅ Icons ready"

# ── 6. Build ──────────────────────────────────────────────────────────────────
echo ""
echo "🔨 Building Tauri desktop app…"
echo "   This may take 5-10 minutes on first build (Rust compile)."
echo ""

cd "$ROOT"

# Use cargo tauri build
TAURI_PRIVATE_KEY="" cargo tauri build 2>&1 | while IFS= read -r line; do
  echo "  $line"
done

BUILD_EXIT=${PIPESTATUS[0]}

if [ $BUILD_EXIT -eq 0 ]; then
  echo ""
  echo "╔══════════════════════════════════════════════════╗"
  echo "║        ✅ Tauri Build Complete!                  ║"
  echo "╚══════════════════════════════════════════════════╝"
  echo ""
  
  # Find the built artifact
  if [ "$(uname)" = "Darwin" ]; then
    ARTIFACT=$(find "$ROOT/src-tauri/target/release/bundle" -name "*.dmg" 2>/dev/null | head -1)
    APP=$(find "$ROOT/src-tauri/target/release/bundle" -name "*.app" 2>/dev/null | head -1)
    echo "📦 macOS DMG: $ARTIFACT"
    echo "📦 macOS App: $APP"
  elif [[ "$(uname)" == "Linux"* ]]; then
    ARTIFACT=$(find "$ROOT/src-tauri/target/release/bundle" -name "*.deb" -o -name "*.AppImage" 2>/dev/null | head -1)
    echo "📦 Linux package: $ARTIFACT"
  else
    ARTIFACT=$(find "$ROOT/src-tauri/target/release/bundle" -name "*.msi" -o -name "*.exe" 2>/dev/null | head -1)
    echo "📦 Windows installer: $ARTIFACT"
  fi
  
  echo ""
  echo "To run in dev mode: cargo tauri dev"
  echo "Built artifacts in: src-tauri/target/release/bundle/"
else
  echo ""
  echo "❌ Build failed (exit $BUILD_EXIT)"
  echo ""
  echo "Common fixes:"
  echo "  1. Rust toolchain: rustup update stable"
  echo "  2. Missing deps (Linux): sudo apt install libwebkit2gtk-4.0-dev libssl-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev"
  echo "  3. Missing deps (macOS): xcode-select --install"
  echo "  4. Check src-tauri/tauri.conf.json is valid"
  exit $BUILD_EXIT
fi
