"""Proves the sample-lineage parser maps MusicBrainz recording relationships
correctly: 'forward' → this track SAMPLES the original; 'backward' → this track
is SAMPLED IN the other. No network — feeds a crafted MB payload to the pure
parser.

Run:  /opt/anaconda3/bin/python test_sample_lookup.py
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sample_lookup as sl

fails = []
def chk(c, m): print(("  PASS  " if c else "  FAIL  ") + m); (None if c else fails.append(m))

# A realistic MusicBrainz relations array for a recording lookup with recording-rels.
relations = [
    {  # this recording SAMPLES the James Brown original
        "type": "samples", "direction": "forward",
        "attributes": ["partial"],
        "recording": {"id": "jb-mbid", "title": "Funky Drummer",
                      "artist-credit": [{"name": "James Brown"}]},
    },
    {  # this recording IS SAMPLED IN a later track
        "type": "samples", "direction": "backward",
        "recording": {"id": "later-mbid", "title": "Later Banger",
                      "artist-credit": [{"name": "Some"}, {"name": " Producer"}]},
    },
    {  # unrelated relationship type — must be ignored
        "type": "remix of", "direction": "forward",
        "recording": {"id": "x", "title": "Ignore me"},
    },
    {  # malformed (no recording id) — must be skipped
        "type": "samples", "direction": "forward", "recording": {}},
]

samples, sampled_in = sl._parse_sample_relations(relations)

chk(len(samples) == 1 and samples[0]["title"] == "Funky Drummer", "forward 'samples' → the original this track samples")
chk(samples[0]["artist"] == "James Brown", "the original's artist is parsed")
chk(samples[0]["partial"] is True, "'partial' attribute carried through")
chk(len(sampled_in) == 1 and sampled_in[0]["title"] == "Later Banger", "backward 'samples' → what samples this track")
chk(sampled_in[0]["artist"] == "Some Producer", "multi-part artist credit joined")
chk(all(s["mbid"] for s in samples + sampled_in), "every result carries an MBID for linking")
chk(not any("Ignore" in (s.get("title") or "") for s in samples + sampled_in), "non-sample relationships ignored")

# empty / None inputs never raise
chk(sl._parse_sample_relations(None) == ([], []), "None relations → empty, no crash")

print("\nRESULT:", "ALL PASS — sample lineage parsed + directional mapping correct"
      if not fails else f"{len(fails)} FAILURES")
sys.exit(1 if fails else 0)
