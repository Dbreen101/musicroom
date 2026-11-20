// =============================================================
// audio_coord.js — single-active-player lock across windows.
//
// Multiple windows of Music Room (main app + Seinnteoir popout)
// each have their own <audio> element. Without coordination, hitting
// play in one would not stop the other and you'd get music layered
// on music. This module gives every player a single shared lock:
//
//   AudioCoord.claim('the Seinnteoir')   // → true if you may play
//   AudioCoord.release()                  // when you pause/stop
//   AudioCoord.heartbeat()                // call periodically while playing
//   AudioCoord.onPauseRequest(fn)         // run when another window asks
//                                         // you to yield
//
// claim() pops a confirm() if another window holds the lock,
// asks the user to pause that one. If they say yes, it sends a
// "pause-please" broadcast and waits briefly for the other to
// release before granting.
//
// Lock survives navigation (localStorage) AND stale owners are
// auto-evicted after 6 s with no heartbeat.
// =============================================================
(function () {
'use strict';

const LS_KEY     = 'mr_audio_owner_v1';
const CH_NAME    = 'mr-audio-coord-v1';
const STALE_MS   = 6000;
const HEARTBEAT  = 2500;

const SELF_ID = 'p_' + Math.random().toString(36).slice(2, 9);
let channel;
try { channel = new BroadcastChannel(CH_NAME); } catch (_) { channel = null; }

let _selfLabel    = '';
let _heartbeatTimer = null;
let _pauseHandlers  = [];

function _readOwner() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || 'null'); }
    catch { return null; }
}
function _writeOwner(owner) {
    try {
        if (owner) localStorage.setItem(LS_KEY, JSON.stringify(owner));
        else       localStorage.removeItem(LS_KEY);
    } catch (_) {}
}
function _isStale(owner) {
    if (!owner) return true;
    return Date.now() - (owner.ts || 0) > STALE_MS;
}

function _setOwnerSelf(label) {
    _selfLabel = label || _selfLabel;
    _writeOwner({ id: SELF_ID, label: _selfLabel, ts: Date.now() });
    _bcast({ type: 'playing', id: SELF_ID, label: _selfLabel });
    if (!_heartbeatTimer) {
        _heartbeatTimer = setInterval(() => {
            // Only heartbeat if we still own the lock
            const o = _readOwner();
            if (o && o.id === SELF_ID) {
                _writeOwner({ id: SELF_ID, label: _selfLabel, ts: Date.now() });
            } else {
                clearInterval(_heartbeatTimer);
                _heartbeatTimer = null;
            }
        }, HEARTBEAT);
    }
}

function _bcast(msg) { if (channel) try { channel.postMessage(msg); } catch (_) {} }

async function claim(label) {
    const owner = _readOwner();
    // No one, or stale, or self → take it
    if (!owner || owner.id === SELF_ID || _isStale(owner)) {
        _setOwnerSelf(label);
        return true;
    }
    // Someone else is playing. Ask the user.
    const otherLabel = owner.label || 'another player';
    let ok;
    try {
        ok = window.confirm(`Pause ${otherLabel} and play here instead?`);
    } catch (_) {
        ok = true; // headless / no confirm available
    }
    if (!ok) return false;
    // Ask the other window to pause
    _bcast({ type: 'pause-please', target: owner.id, from: SELF_ID });
    // Brief wait for the other side to release the lock
    const t0 = Date.now();
    while (Date.now() - t0 < 600) {
        await new Promise(r => setTimeout(r, 40));
        const cur = _readOwner();
        if (!cur || cur.id === SELF_ID || _isStale(cur)) break;
    }
    _setOwnerSelf(label);
    return true;
}

function heartbeat(label) {
    // Forcefully assert ownership (used after a play() succeeds)
    _setOwnerSelf(label);
}

function release() {
    const owner = _readOwner();
    if (owner && owner.id === SELF_ID) {
        _writeOwner(null);
        _bcast({ type: 'released', id: SELF_ID });
    }
    if (_heartbeatTimer) { clearInterval(_heartbeatTimer); _heartbeatTimer = null; }
}

function isSelf() {
    const owner = _readOwner();
    return !!(owner && owner.id === SELF_ID);
}

function currentOwnerLabel() {
    const owner = _readOwner();
    if (!owner || _isStale(owner)) return null;
    if (owner.id === SELF_ID) return null;
    return owner.label || 'another player';
}

function onPauseRequest(fn) {
    if (typeof fn === 'function') _pauseHandlers.push(fn);
}

if (channel) {
    channel.addEventListener('message', (e) => {
        const d = e.data || {};
        if (d.type === 'pause-please' && d.target === SELF_ID) {
            _pauseHandlers.forEach(fn => { try { fn(d); } catch (_) {} });
        }
    });
}

// Release if we held the lock when the window goes away
window.addEventListener('pagehide', release);
window.addEventListener('beforeunload', release);

window.AudioCoord = {
    SELF_ID, claim, release, heartbeat, isSelf,
    currentOwnerLabel, onPauseRequest,
};

})();
