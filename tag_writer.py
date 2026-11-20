"""
=============================================================
MUSIC ROOM — tag_writer.py
=============================================================
What this file does:
    Writes metadata from the Music Room database back into
    the actual audio file tags on disk.

    Called by app.py when the user clicks "Write to file"
    after editing track metadata in the interface.

    Uses mutagen to write tags — supports MP3 (ID3), FLAC
    (Vorbis), M4A (MP4 atoms) and WAV (ID3 in a RIFF chunk).

    Fields written:
        title, artist_name, album, year, track_number, label

    Fields NOT written back (they live only in the database):
        notes, tags, DSP links, colour codes, vinyl info,
        discovered_via — these are Music Room specific and
        don't have standard tag equivalents.
=============================================================
"""

import os
from mutagen.mp3  import MP3
from mutagen.id3  import ID3, TIT2, TPE1, TALB, TDRC, TRCK, TCON
from mutagen.flac import FLAC


def write_tags_to_file(file_path, title=None, artist=None,
                        album=None, year=None, track_number=None):
    """
    Writes metadata into an audio file's embedded tags.

    Only writes fields that are provided — None values are
    skipped, leaving existing tags untouched.

    Returns (success, error_message)
    """
    if not os.path.exists(file_path):
        return False, f"File not found: {file_path}"

    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == ".mp3":
            return _write_mp3_tags(
                file_path, title, artist, album, year, track_number
            )
        elif ext == ".flac":
            return _write_flac_tags(
                file_path, title, artist, album, year, track_number
            )
        elif ext == ".m4a":
            return _write_m4a_tags(
                file_path, title, artist, album, year, track_number
            )
        elif ext == ".wav":
            return _write_wav_tags(
                file_path, title, artist, album, year, track_number
            )
        else:
            return False, f"Unsupported format: {ext}"

    except Exception as e:
        return False, str(e)


def _write_mp3_tags(file_path, title, artist, album, year, track_number):
    """Writes ID3 tags to an MP3 file."""
    try:
        tags = ID3(file_path)
    except Exception:
        # File has no ID3 tags yet — create them
        tags = ID3()

    if title:
        tags["TIT2"] = TIT2(encoding=3, text=title)
    if artist:
        tags["TPE1"] = TPE1(encoding=3, text=artist)
    if album:
        tags["TALB"] = TALB(encoding=3, text=album)
    if year:
        tags["TDRC"] = TDRC(encoding=3, text=str(year))
    if track_number:
        tags["TRCK"] = TRCK(encoding=3, text=str(track_number))

    tags.save(file_path)
    return True, None


def _write_flac_tags(file_path, title, artist, album, year, track_number):
    """Writes Vorbis comment tags to a FLAC file."""
    audio = FLAC(file_path)

    if title:
        audio["title"] = title
    if artist:
        audio["artist"] = artist
    if album:
        audio["album"] = album
    if year:
        audio["date"] = str(year)
    if track_number:
        audio["tracknumber"] = str(track_number)

    audio.save()
    return True, None


def _write_m4a_tags(file_path, title, artist, album, year, track_number):
    """Writes iTunes-style MP4 atoms to an M4A file."""
    from mutagen.mp4 import MP4
    audio = MP4(file_path)
    if audio.tags is None:
        audio.add_tags()

    if title:
        audio["\xa9nam"] = [title]
    if artist:
        audio["\xa9ART"] = [artist]
    if album:
        audio["\xa9alb"] = [album]
    if year:
        audio["\xa9day"] = [str(year)]
    if track_number:
        # MP4 stores track number as (number, total) tuples
        try:
            n = int(str(track_number).split("/")[0])
            audio["trkn"] = [(n, 0)]
        except (ValueError, TypeError):
            pass

    audio.save()
    return True, None


def _write_wav_tags(file_path, title, artist, album, year, track_number):
    """Writes ID3 tags into a WAV file's RIFF chunk.

    WAV has no native tag format; mutagen stores ID3 frames in an 'id3 '
    chunk, the same convention most taggers use. Not every player reads
    them, but Music Room (and our own re-import) will."""
    from mutagen.wave import WAVE
    audio = WAVE(file_path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags     # an ID3 instance — same frames as MP3

    if title:
        tags["TIT2"] = TIT2(encoding=3, text=title)
    if artist:
        tags["TPE1"] = TPE1(encoding=3, text=artist)
    if album:
        tags["TALB"] = TALB(encoding=3, text=album)
    if year:
        tags["TDRC"] = TDRC(encoding=3, text=str(year))
    if track_number:
        tags["TRCK"] = TRCK(encoding=3, text=str(track_number))

    audio.save()
    return True, None
