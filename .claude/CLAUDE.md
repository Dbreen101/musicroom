# Read this first: this folder is the Music Room app's own code

The Music Room works like Ableton Live: the app is finished, and people add to it
from outside. Nobody makes their own version of it.

## If the person wants a plug-in, a look for their music room, or a theme

That is **not** a change to this code, and it never needs a copy of the app.
Plug-ins, room looks (CSS, or a whole page of HTML), the person's own look of the
app and themes are made in a folder of their own, **the workshop**, and brought
into the app they already have installed with its own buttons (Explore → Plug-ins
→ Add a plug-in…, My Public Room → Code → Open a file…, Settings → Your own look →
Open a file…, ◐ → Import a theme…).

So, for them, do none of this: build, run, copy, fork or change this code; start
a server; make a "version", demo, mock-up or website of the app. Instead:

1. Tell them the workshop is the way: the `workshop/` folder here (or
   *Music.Room.workshop.zip* on the Releases page). Copy that folder somewhere
   outside this one and open Claude Code in the copy. Its CLAUDE.md has
   everything, and its settings keep Claude out of the app.
2. Stop. The guide for people is `docs/MAKERS.md`.

## Changing the app itself

Only when the person says they are working on the Music Room itself (fixing it,
or adding to it, to send to Daithí as a pull request: `CONTRIBUTING.md`). Then
this is the map of the code:

@../AGENTS.md
