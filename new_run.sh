#!/bin/bash
# new_run.sh
# ----------
# Archives the previous fermentation run and starts a fresh one.
# BSC project – Ruben Schmid
#
# Usage:
#   bash new_run.sh
#   bash new_run.sh run_2        # optionally pass run name directly

DATA_DIR="/home/schmiru/Kombucha_Fermentation"
CODE_DIR="/home/schmiru/BSC_Raspberry"
VENV="$CODE_DIR/venv/bin/python3"

echo "======================================"
echo "  Kombucha – New Run Setup"
echo "======================================"

# ── Stop current run ──────────────────────────────────────────
echo ""
echo "Stopping current run..."
sudo systemctl stop kombucha 2>/dev/null && echo "  systemctl stopped" || echo "  (service not running)"
screen -S kombucha -X quit 2>/dev/null && echo "  screen stopped" || true

# ── Archive previous data if it exists ───────────────────────
if [ -f "$DATA_DIR/sensor_log.csv" ] || [ -d "$DATA_DIR/images" ]; then
    echo ""

    # Get run name
    if [ -n "$1" ]; then
        RUN_NAME="$1"
    else
        read -p "Enter a name for this archived run (e.g. run_1, test_batch): " RUN_NAME
        RUN_NAME="${RUN_NAME:-run_$(date +%Y%m%d_%H%M%S)}"
    fi

    ARCHIVE="$DATA_DIR/$RUN_NAME"
    mkdir -p "$ARCHIVE"

    [ -f "$DATA_DIR/sensor_log.csv" ]        && mv "$DATA_DIR/sensor_log.csv"        "$ARCHIVE/" && echo "  Archived sensor_log.csv"
    [ -d "$DATA_DIR/images" ]                && mv "$DATA_DIR/images"                "$ARCHIVE/" && echo "  Archived images/"
    [ -f "$DATA_DIR/.start_time" ]           && mv "$DATA_DIR/.start_time"           "$ARCHIVE/" && echo "  Archived .start_time"
    [ -f "$DATA_DIR/calibration.json" ]      && mv "$DATA_DIR/calibration.json"      "$ARCHIVE/" && echo "  Archived calibration.json"
    [ -f "$DATA_DIR/ph_verification.json" ]  && mv "$DATA_DIR/ph_verification.json"  "$ARCHIVE/" && echo "  Archived ph_verification.json"
    [ -f "$DATA_DIR/simulation_curve.csv" ]  && cp "$DATA_DIR/simulation_curve.csv"  "$ARCHIVE/" && echo "  Copied simulation_curve.csv"

    echo "  → Saved to $ARCHIVE"
else
    echo ""
    echo "  No previous run data found — starting fresh."
fi

# ── pH probe verification ─────────────────────────────────────
echo ""
echo "======================================"
echo "  pH Probe Verification"
echo "======================================"
read -p "  Run verify_ph.py? [y/s to skip]: " DO_PH
if [ "$DO_PH" = "y" ]; then
    python3 "$CODE_DIR/verify_ph.py" --save "$DATA_DIR/ph_verification.json"
else
    echo "  Skipped — remember to verify the probe manually before starting."
fi

# ── Show current recipe ───────────────────────────────────────
echo ""
echo "======================================"
echo "  Current recipe in main_loop.py:"
echo "======================================"
grep -A 10 "RECIPE = SimConfig" "$CODE_DIR/main_loop.py" | head -12
echo ""
read -p "Do you want to edit the recipe before starting? [y/n]: " EDIT
if [ "$EDIT" = "y" ]; then
    nano "$CODE_DIR/main_loop.py"
fi

# ── Start new run ─────────────────────────────────────────────
echo ""
read -p "Start new run now? [y/n]: " START
if [ "$START" = "y" ]; then
    # Try systemctl first, fall back to screen
    if systemctl is-enabled kombucha &>/dev/null; then
        sudo systemctl start kombucha
        echo "  Started via systemctl"
        echo "  View logs: journalctl -u kombucha -f"
    else
        screen -dmS kombucha bash -c "cd $CODE_DIR && source venv/bin/activate && python3 main_loop.py"
        echo "  Started in screen session 'kombucha'"
        echo "  Reattach with: screen -r kombucha"
    fi
    echo ""
    echo "  Run started! Good luck with the fermentation :)"
else
    echo "  Run not started. Start manually with:"
    echo "    sudo systemctl start kombucha"
    echo "  or:"
    echo "    screen -S kombucha"
    echo "    python3 main_loop.py"
fi

echo "======================================"
