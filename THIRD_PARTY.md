# Third-party code, data and fonts

The Music Room's own code is under the GNU AGPL-3.0 ([LICENSE](LICENSE)).
These parts it carries are other people's work, under their own licences:

| what | where | licence |
|---|---|---|
| three.js | `static/vendor/three/` | MIT |
| three-globe | `static/vendor/map/three-globe.min.js` | MIT |
| SortableJS | `static/vendor/sortable/` | MIT |
| GSAP | `static/vendor/gsap/` | GSAP's own Standard License (gsap.com/standard-license) — free to use, not open source |
| Natural Earth (coasts, lakes, rivers, towns, countries) | `static/data/isles.json`, `static/data/globe_land.png`, `static/vendor/map/ne_110m_countries.json` | public domain |
| Earth picture for the old globe | `static/vendor/map/earth.jpg` | NASA Blue Marble, public domain |
| IBM Plex Mono, Instrument Serif and the other fonts | `static/fonts/` | SIL Open Font License 1.1 (each folder's `OFL.txt`; `static/fonts/ui/` holds the OFL faces Google Fonts serves) |
| ffmpeg (inside the ready-made app only) | from `imageio-ffmpeg` | GPL / LGPL |

Python libraries come from `requirements.txt`, each under its own licence.
The list of known AI-generated artist accounts the app can fetch
(github.com/eye-wave/spotify-ai-blocklist) is fetched at run time, never
carried in this code.
