#!/bin/bash
# Music Room GR1 — the Green Room residency build, in dev.
#
# The p1 3D app with the Green Room switched on (MR_GREEN_ROOM=1: Green Room
# in the nav, no recorder), on its own port so it sits alongside the other
# dev instances. Also starts the DEV pool server (green_room_dev.db, test
# records only) on 5301 if nothing is there yet — the real campus pool is
# gr_server.py run against green_room.db, started by hand.
#
# Desktop launcher: "music room gr1 dev.command".

cd "$(dirname "$0")" || exit 1
source venv/bin/activate

if ! curl -s -m 1 -o /dev/null http://127.0.0.1:5301/; then
    MR_GR_DB="$PWD/green_room_dev.db" nohup python3 gr_server.py run --host 127.0.0.1 --port 5301 \
        > /tmp/music_room_gr_dev_pool.log 2>&1 &
fi

export MUSICROOM_3D=1
export MR_GREEN_ROOM=1
export MR_GR_VERSION=GR1
export MUSICROOM_PORT=5181
exec python3 desktop.py
