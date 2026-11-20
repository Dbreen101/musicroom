#!/bin/bash
# Music Room 3D — the Prototype-1 3D-only instance.
#
# Same code, same library, different front door: every surface with a 3D
# equivalent serves the 3D version, and the room opens everything else as
# an overlay over itself. Runs on its own port so it can sit alongside the
# regular app. Double-click "Music Room 3D.command" on the Desktop to launch.

cd "$(dirname "$0")" || exit 1
source venv/bin/activate
export MUSICROOM_3D=1
export MUSICROOM_PORT=5180
exec python3 desktop.py
