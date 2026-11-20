# Bundled fonts

Every typeface here is licensed under the **SIL Open Font License, Version 1.1**
(OFL), which permits using, bundling, redistributing and shipping the font inside
an application — including one that is sold — provided each font's `OFL.txt`
travels with it (it does, in each folder) and the font is never sold on its own.
So these are safe to include in the Music Room prototype and any app distributed
or sold from it.

They power the per-cover record typography (`RECORD_FONTS` in
`templates/room3d.html`) and the Settings → "Record typography" picker, declared
as `@font-face` in `static/css/record_fonts.css` and served locally (no CDN, works
offline). Files are shipped **verbatim** — unmodified — so the Reserved Font Name
clause on some of them is not triggered.

| Folder | Family | Source |
| --- | --- | --- |
| fraunces | Fraunces | github.com/undercasetype/Fraunces |
| youngserif | Young Serif | github.com/noirblancrouge/YoungSerif |
| instrumentserif | Instrument Serif | github.com/Instrument/instrument-serif |
| gloock | Gloock | github.com/duartp/gloock (via Google Fonts) |
| bagnard | Bagnard | github.com/sebsan/Bagnard |
| basteleur | Basteleur | gitlab.com/velvetyne/basteleur |
| nyghtserif | Nyght Serif | gitlab.com/mkobuzan/nyght-serif (Tunera) |
| sortsmillgoudy | Sorts Mill Goudy | github.com/theleagueof/sorts-mill-goudy |
| bricolage | Bricolage Grotesque | github.com/ateliertriay/bricolage |
| apfelgrotezk | Apfel Grotezk | github.com/collletttivo/apfel-grotezk |
| lemurmure | Le Murmure | gitlab.com/velvetyne/murmure |
| leaguegothic | League Gothic | github.com/theleagueof/league-gothic |

To drop a face: delete its folder, its `@font-face` in
`static/css/record_fonts.css`, its entry in `RECORD_FONTS` (room3d.html) and its
`<option>` in the Settings picker (settings.html).
