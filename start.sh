#!/bin/bash
# Music Room — start script
# Run this once after pulling new code: ./start.sh
# It installs any missing dependencies, migrates the DB, and starts the server.

set -e
cd "$(dirname "$0")"

source venv/bin/activate

echo ""
echo "============================================================="
echo "  Music Room — checking dependencies"
echo "============================================================="

# Whisper (for voice note transcription)
python3 -c "import whisper" 2>/dev/null || {
    echo "  Installing openai-whisper..."
    pip install openai-whisper --quiet
}

echo "  Dependencies OK"
echo ""

python3 migrate.py
python3 app.py
