#!/usr/bin/env bash
# run-sandboxed.sh
#
# Runs Google Antigravity CLI (agy) inside a bubblewrap (bwrap) sandbox with:
# - Full filesystem READ-ONLY by default
# - Current workspace ($PWD) mounted READ-WRITE
# - agy state (~/.gemini) mounted READ-WRITE
# - Isolated /tmp (tmpfs), /proc, /dev
# - Network access enabled for Gemini API calls
# - Automatic --dangerously-skip-permissions passed to agy so it executes without prompts

set -euo pipefail

# Locate agy binary
AGY_BIN="${AGY_BIN:-$(command -v agy || echo "$HOME/.local/bin/agy")}"
if [[ ! -x "$AGY_BIN" ]]; then
    echo "Error: agy binary not found in PATH or $HOME/.local/bin/agy" >&2
    exit 1
fi

if ! command -v bwrap >/dev/null 2>&1; then
    echo "Error: bubblewrap (bwrap) is not installed." >&2
    exit 1
fi

WORKSPACE="${INFAPLA_DATA_DIR:-${WORKSPACE:-$PWD}}"
mkdir -p "$HOME/.gemini"

# Optional bindings for user configurations if they exist
EXTRA_BINDS=()
if [[ -d "$HOME/.config" ]]; then
    EXTRA_BINDS+=(--ro-bind "$HOME/.config" "$HOME/.config")
fi
if [[ -f "$HOME/.gitconfig" ]]; then
    EXTRA_BINDS+=(--ro-bind "$HOME/.gitconfig" "$HOME/.gitconfig")
fi

echo "==========================================================" >&2
echo " Starting Antigravity (agy) in Bubblewrap Sandbox" >&2
echo " Workspace (RW): $WORKSPACE" >&2
echo " System root:    READ-ONLY" >&2
echo " agy permissions: --dangerously-skip-permissions" >&2
echo "==========================================================" >&2

exec bwrap \
    --die-with-parent \
    --unshare-pid \
    --ro-bind / / \
    --dev /dev \
    --proc /proc \
    --tmpfs /tmp \
    --bind "$WORKSPACE" "$WORKSPACE" \
    --bind "$HOME/.gemini" "$HOME/.gemini" \
    "${EXTRA_BINDS[@]}" \
    --chdir "$WORKSPACE" \
    "$AGY_BIN" \
    --dangerously-skip-permissions \
    "$@"
