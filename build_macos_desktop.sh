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

# Resolve the repository root ONCE, at the top, before any `cd`.
#
# This must happen here and nowhere else. ${BASH_SOURCE[0]} is whatever the
# user typed -- normally the relative "./build_macos_desktop.sh", whose dirname
# is ".". Resolving that AFTER the script has already done `cd src-tauri` makes
# REPO_ROOT point at src-tauri/, and every path built from it is wrong.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🍏 ====================================================================="
echo "🍏  Agentic OS Platform v10.0 — macOS Native Application Builder"
echo "🍏  Created by Joshua Strickland & Strick Tech"
echo "🍏 ====================================================================="
echo ""

BUNDLE_PYTHON=0
SIGN_APP=0
NOTARIZE_APP=0

usage() {
  cat <<'USAGE'
Usage: ./build_macos_desktop.sh [options]

Builds the Agentic OS Platform macOS desktop application (.app, and a .dmg
when bundle_dmg.sh succeeds).

Options:
  --bundle-python   Download and bundle a standalone Python runtime inside the
                    .app so the app runs on a machine with no Python installed.
  --sign            Code-sign using $APPLE_SIGNING_IDENTITY.
  --notarize        Notarize using $APPLE_ID, $APPLE_PASSWORD, $APPLE_TEAM_ID.
  -h, --help        Show this message and exit.

After a successful build:
  open "src-tauri/target/release/bundle/macos/Agentic OS Platform.app"
USAGE
}

for arg in "$@"; do
  case $arg in
    -h|--help) usage; exit 0 ;;
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
mkdir -p src-tauri/python_embedded
if [ ! -f "src-tauri/icons/32x32.png" ] || [ ! -f "src-tauri/icons/icon.icns" ]; then
  echo "🎨 Generating native desktop application icons..."
  python3 -c "
import os
from PIL import Image, ImageDraw

os.makedirs('src-tauri/icons', exist_ok=True)
base = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
draw = ImageDraw.Draw(base)
draw.rounded_rectangle([64, 64, 960, 960], radius=180, fill=(13, 18, 36, 255), outline=(91, 138, 248, 255), width=16)
draw.ellipse([256, 256, 768, 768], fill=(22, 32, 64, 255), outline=(76, 201, 138, 255), width=12)
draw.ellipse([412, 412, 612, 612], fill=(91, 138, 248, 255))
base.resize((32, 32), Image.Resampling.LANCZOS).save('src-tauri/icons/32x32.png')
base.resize((128, 128), Image.Resampling.LANCZOS).save('src-tauri/icons/128x128.png')
base.resize((256, 256), Image.Resampling.LANCZOS).save('src-tauri/icons/128x128@2x.png')
base.resize((512, 512), Image.Resampling.LANCZOS).save('src-tauri/icons/icon.png')
base.save('src-tauri/icons/icon.icns')
base.resize((256, 256), Image.Resampling.LANCZOS).save('src-tauri/icons/icon.ico')
"
fi
cd src-tauri
mkdir -p python_embedded

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

# ─────────────────────────────────────────────────────────────────────────────
# Rebuild the frontend bundle. NOT optional.
#
# backend/app.py serves a REWRITTEN index.html that points at content-hashed
# bundles in frontend/dist. If dist is stale, the packaged app runs old
# JavaScript even though every source file on disk is current -- which is how
# a fully-unlocked build still shows the Pro/upgrade popup.
#
# This is a hard failure rather than a warning: shipping a silently stale
# frontend is worse than not shipping.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
# ── Gate 0: are we even building what the user thinks we are? ────────────────
#
# A user ran `git pull` five times and got the same stale app every time. The
# pull was FAILING each time -- "local changes would be overwritten by merge",
# frontend/dist -- and the failure scrolled past above the build output, which
# then reported complete success. Five fixes never reached their machine while
# every build said it worked.
#
# Being behind origin is not automatically wrong (offline, deliberate pin), so
# this warns loudly rather than refusing. But it must never again be silent.
if command -v git >/dev/null 2>&1 && [ -d "$REPO_ROOT/.git" ]; then
  (
    cd "$REPO_ROOT" || exit 0
    _branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
    git fetch -q origin "$_branch" 2>/dev/null || true
    _behind=$(git rev-list --count "HEAD..origin/$_branch" 2>/dev/null || echo 0)
    _dirty=$(git status --porcelain -- frontend/dist 2>/dev/null | wc -l | tr -d ' ')

    if [ "${_behind:-0}" -gt 0 ]; then
      echo ""
      echo "⚠️  YOU ARE $_behind COMMIT(S) BEHIND origin/$_branch."
      echo "    This build will NOT contain those changes."
      git --no-pager log --oneline "HEAD..origin/$_branch" 2>/dev/null | sed 's/^/      /'
      if [ "${_dirty:-0}" -gt 0 ]; then
        echo ""
        echo "    Cause: $_dirty modified file(s) in frontend/dist are blocking the"
        echo "    merge. These are BUILD OUTPUT -- discarding them is always safe."
        echo "    Fix:"
        echo "      git checkout -- frontend/dist && git pull origin $_branch"
      else
        echo "    Fix:  git pull origin $_branch"
      fi
      echo ""
      printf "    Continue with the STALE build anyway? [y/N] "
      if [ -t 0 ]; then
        read -r _ans
        case "$_ans" in
          y|Y|yes|YES) echo "    Continuing." ;;
          *) echo "    Stopped. Pull, then re-run."; exit 97 ;;
        esac
      else
        echo "    (non-interactive: continuing, but the build IS stale)"
      fi
    fi
  )
  _gate_rc=$?
  if [ "$_gate_rc" -eq 97 ]; then exit 1; fi
fi

echo "🧩 Rebuilding the frontend bundle (frontend/dist)..."
# NOTE: we are inside src-tauri/ at this point (line ~134 does `cd src-tauri`).
# These gates MUST run from the repository root or every path below is wrong.
# REPO_ROOT is resolved at the TOP of this script, deliberately: re-deriving it
# here from ${BASH_SOURCE[0]} would resolve "." against src-tauri/ and break.
if [ ! -f "$REPO_ROOT/scripts/build_bundle.py" ]; then
  echo "❌ scripts/build_bundle.py is missing. Cannot verify the frontend bundle."
  echo "   Refusing to package a build whose JavaScript cannot be verified."
  exit 1
fi

if ! (cd "$REPO_ROOT" && python3 scripts/build_bundle.py); then
  echo "❌ Frontend bundle build FAILED."
  echo "   The app would serve stale JavaScript. Fix the error above and retry."
  exit 1
fi

# Second gate: confirm the freshly built bundle actually matches the sources.
if ! (cd "$REPO_ROOT" && python3 scripts/build_bundle.py --check); then
  echo "❌ The bundle is still stale after rebuilding."
  echo "   Refusing to package: the app would serve JavaScript that does not"
  echo "   match frontend/js/. Run 'python3 scripts/build_bundle.py' and"
  echo "   investigate before building again."
  exit 1
fi

# Third gate: a content canary. The bundle can be internally consistent and
# still predate the unlock if someone builds from an old checkout, so assert
# a string that only exists in the current frontend.
if ! grep -q "CORE MODULES" "$REPO_ROOT/frontend/index.html"; then
  echo "❌ frontend/index.html does not contain 'CORE MODULES'."
  echo "   This checkout predates the licence unlock. Pull the latest main:"
  echo "     git pull origin main"
  exit 1
fi
echo "✅ Frontend bundle rebuilt and verified against source."
echo ""

# Apply Apple Code Signing Configuration if requested
# The .app is the deliverable. The .dmg is a convenience wrapper, and
# bundle_dmg.sh fails for reasons that have nothing to do with the build:
# a stale /Volumes mount, no GUI session, an AppleScript/Finder timeout.
# `set -e` used to abort here, which skipped the copy step below and left
# the user with no app at the documented path even though the binary and
# the .app had both built successfully.
# So: do not let a DMG failure destroy a good .app build.
set +e
if [ "$SIGN_APP" -eq 1 ] && [ -n "$APPLE_SIGNING_IDENTITY" ]; then
  echo "✍️  Signing identity provided: $APPLE_SIGNING_IDENTITY"
  cargo tauri build "${BUILD_FLAGS[@]}" --config '{"bundle": {"macOS": {"signingIdentity": "'"$APPLE_SIGNING_IDENTITY"'"}}}'
else
  cargo tauri build "${BUILD_FLAGS[@]}"
fi
TAURI_BUILD_RC=$?
set -e

if [ "$TAURI_BUILD_RC" -ne 0 ]; then
  # Did the .app survive? If so this was a DMG-only failure, which is benign.
  APP_CHECK=$(find target -name "*.app" -maxdepth 5 2>/dev/null | head -n 1)
  if [ -n "$APP_CHECK" ]; then
    echo ""
    echo "⚠️  cargo tauri build exited $TAURI_BUILD_RC, but the .app bundle WAS produced:"
    echo "      $APP_CHECK"
    echo "    This is almost always bundle_dmg.sh failing (stale /Volumes mount,"
    echo "    no GUI session, or a Finder/AppleScript timeout). The .app is fine."
    echo "    Continuing so the app is installed at the documented path."
    echo "    If you need the .dmg, unmount any 'Agentic OS' volume and re-run:"
    echo "      hdiutil detach /Volumes/Agentic\\ OS\\ Platform 2>/dev/null; true"
    echo ""
    DMG_BUILD_FAILED=1
  else
    echo "❌ cargo tauri build failed ($TAURI_BUILD_RC) and produced no .app bundle."
    exit "$TAURI_BUILD_RC"
  fi
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

# Locate the artefacts. Two traps here, both hit in real builds:
#
# 1. A failed bundle_dmg.sh leaves a partial or stale .dmg from an earlier
#    attempt on disk. A bare `find -name "*.dmg"` finds it, and the summary then
#    claims a DMG was built in the same breath as warning that it was not. If
#    the DMG step failed, there is no DMG -- do not go looking for one.
#
# 2. bundle_dmg.sh stages a COPY of the .app inside its own working directory
#    (bundle/dmg/<name>/Agentic OS Platform.app). `find -name "*.app" | head -1`
#    can return that staging copy rather than the real bundle, depending on
#    directory order -- so the script could copy a half-staged app over the good
#    one. Restrict the search to bundle/macos, the only place the genuine .app
#    is emitted, and fall back to the broad search only if that finds nothing.
# WHICH .app -- this must be deterministic, and it was not.
#
# `src-tauri/target/release/bundle/macos/` is BOTH a place cargo can emit to
# AND the destination this script copies to for a stable documented path. On
# every build after the first it already contains LAST build's app. So the
# search had two hits:
#
#   target/aarch64-apple-darwin/release/bundle/macos/...  <- what cargo just built
#   target/release/bundle/macos/...                       <- last build's copy
#
# and `head -n 1` chose between them by filesystem iteration order. When the
# stale one won, the script copied it over itself, the != guard skipped the
# copy, and the user opened an app containing OLD JavaScript -- with every
# build reporting complete success.
#
# Sorting by mtime does NOT fix this: the destination is touched by the copy
# itself, so the stale copy is frequently the newest thing on disk. Verified.
#
# The only correct answer is to know where cargo was told to build. BUILD_FLAGS
# carries --target when we set it, so derive the path rather than search for it,
# and explicitly exclude the destination from any fallback search.
CARGO_TARGET_DIR_NAME=""
for _i in "${!BUILD_FLAGS[@]}"; do
  if [ "${BUILD_FLAGS[$_i]}" = "--target" ]; then
    CARGO_TARGET_DIR_NAME="${BUILD_FLAGS[$((_i+1))]}"
  fi
done

APP_FOUND=""
if [ -n "$CARGO_TARGET_DIR_NAME" ]; then
  APP_FOUND=$(find "src-tauri/target/$CARGO_TARGET_DIR_NAME/release/bundle/macos" \
                -maxdepth 1 -name "*.app" -prune 2>/dev/null | head -n 1)
fi
if [ -z "$APP_FOUND" ]; then
  # No explicit --target (cargo emitted to target/release), or the arch path is
  # absent. Search everywhere EXCEPT the destination, so we can never select
  # the previous build's copy.
  APP_FOUND=$(find src-tauri/target -path "*/bundle/macos/*.app" -prune 2>/dev/null \
                | grep -v "^src-tauri/target/release/bundle/macos/" | head -n 1)
fi
if [ -z "$APP_FOUND" ]; then
  # Genuinely only the default target dir exists -- that IS the real build.
  APP_FOUND=$(find src-tauri/target -path "*/bundle/macos/*.app" -prune 2>/dev/null | head -n 1)
fi

if [ "${DMG_BUILD_FAILED:-0}" -eq 1 ]; then
  DMG_FOUND=""
else
  DMG_FOUND=$(find src-tauri/target -path "*/bundle/dmg/*.dmg" 2>/dev/null | head -n 1)
fi

# Ensure standard target/release paths exist for universal / aarch64 consistency
mkdir -p src-tauri/target/release/bundle/macos
mkdir -p src-tauri/target/release/bundle/dmg

if [ -n "$APP_FOUND" ] && [ "$APP_FOUND" != "src-tauri/target/release/bundle/macos/Agentic OS Platform.app" ]; then
  rm -rf "src-tauri/target/release/bundle/macos/Agentic OS Platform.app"
  cp -R "$APP_FOUND" "src-tauri/target/release/bundle/macos/Agentic OS Platform.app"
fi

if [ -n "$DMG_FOUND" ] && [ "$DMG_FOUND" != "src-tauri/target/release/bundle/dmg/Agentic OS Platform.dmg" ]; then
  rm -f "src-tauri/target/release/bundle/dmg/Agentic OS Platform.dmg"
  cp "$DMG_FOUND" "src-tauri/target/release/bundle/dmg/Agentic OS Platform.dmg"
fi

echo ""
echo "🎉 ====================================================================="
echo "🎉  Agentic OS Platform v11.5.0 macOS Desktop App Built Successfully!"
# Exactly one of these prints. Previously both did, so the summary announced a
# DMG path AND said the DMG had not been built, two lines apart.
if [ "${DMG_BUILD_FAILED:-0}" -eq 1 ] || [ -z "$DMG_FOUND" ]; then
  echo "🎉  ⚠️  DMG Installer : NOT built (bundle_dmg.sh failed — see warning above)."
  echo "🎉      The .app below is complete and installable regardless."
else
  echo "🎉  👉 DMG Installer : src-tauri/target/release/bundle/dmg/Agentic OS Platform.dmg"
fi
if [ -n "$APP_FOUND" ]; then
  echo "🎉  👉 App Bundle    : src-tauri/target/release/bundle/macos/Agentic OS Platform.app"
  echo ""
  echo "🚀  To launch your newly compiled desktop bundle right now, run:"
  echo '    open "src-tauri/target/release/bundle/macos/Agentic OS Platform.app"'
fi
echo "🎉 ====================================================================="
