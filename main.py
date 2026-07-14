#!/usr/bin/env python3
"""
ms_renamer.py — Sample pack renamer with copy-first safety.

Step 0: recursively copy SOURCE_PATH → DEST_PATH (original untouched).
Step 1: detect & strip library prefix from all folder/file names.
Step 2: rename audio files to <TYPE><N>+/-<BPM><KEY>.ext

Output format examples:
  KK1.wav          KK12.wav          PD16-Cm#.wav
  PD16+60Cm#.wav   SH2+22.wav        HH1.wav

Set SOURCE_PATH and DEST_PATH below, then run: python3 main.py
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

SOURCE_PATH = "/Users/v.rusov/Desktop/samples/Splice Sounds - Spinnin' Sounds Tech House Sample Pack"
DEST_PATH   = "/Users/v.rusov/Desktop/samples_out/Tech House Spinnin"

# Leave empty for auto-detection.
LIBRARY_NAME = ""

# ============================================================

# TYPE_WORDS is the source of truth: TYPE → [words that map to it].
# AUTO_REPLACE is built from it automatically each run.
# Edit this dict to add/remove/rename types — conflicts are visible at a glance.
TYPE_WORDS: dict[str, list[str]] = {
    # Drums — hits
    "KK": ["kick", "kicks", "bd"],
    "SN": ["snare", "snares", "snr", "sd"],
    "GH": ["ghost"],
    "HH": ["hat", "hats", "hihat", "hihats", "closedhat", "closed"],
    "OH": ["openhat", "open"],
    "CL": ["clap", "claps", "clp"],
    "TM": ["tom", "toms", "floortom"],
    "RM": ["rim", "rimshot"],
    # Percussion
    "PC": ["perc", "percussion", "percs"],
    "SH": ["shaker", "shakers"],
    "TB": ["tamb", "tambourine", "tambs"],
    "SF": ["shuffle", "shuffles"],
    "CV": ["clave"],
    "CB": ["cowbell"],
    # Cymbals
    "CR": ["crash"],
    "RD": ["ride", "rides"],
    "CY": ["cymbal", "cymbals", "cym"],
    # Bass
    "BS": ["bass", "synthbass"],
    "SB": ["sub"],
    # Tonal / synth
    "SY": ["synth"],
    "AN": ["analog", "analogue"],
    "PN": ["piano"],
    "EP": ["epiano"],
    "KY": ["keys", "key"],
    "PD": ["pad", "pads"],
    "LD": ["lead"],
    "AR": ["arp"],
    "CH": ["chord", "chords"],
    "PK": ["pluck"],
    "ML": ["melody", "melodic"],
    "ST": ["stab", "stabs"],
    # Instruments
    "GT": ["guitar", "guitars"],
    "OR": ["organ"],
    "HR": ["horn", "horns"],
    "BR": ["brush", "brass"],   # brush (drum) and brass (instrument) share BR
    "SR": ["string", "strings"],
    "BL": ["bell", "bells"],
    "SX": ["sax", "saxophone"],
    "FL": ["fill", "flute"],    # fill (drum fill) and flute share FL
    # Loops / FX / Misc
    "LP": ["loop", "loops"],
    "DR": ["drum", "drums"],
    "AT": ["atmo", "atmosphere"],
    "FX": ["fx", "fxs", "effect"],
    "VC": ["vocal", "vocals", "vox", "voice"],
    "CO": ["combi"],
    "TP": ["top"],
    "FU": ["full"],
    "MU": ["music"],
}

AUTO_REPLACE: dict[str, str] = {
    word: abbrev
    for abbrev, words in TYPE_WORDS.items()
    for word in words
}

# Abbreviations that indicate a generic container, not a specific sound.
# Matched last — only if no specific type found in the name.
WEAK_ABBREVS = {"LP", "DR", "MU", "FU", "TP", "SY", "AN"}

AUDIO_EXT = {".wav", ".aif", ".aiff", ".mp3", ".flac", ".ogg"}

# Ableton sidecar files — skip entirely.
_ASD_RE = re.compile(r"\.asd$", re.IGNORECASE)

_RE_KEY = re.compile(
    r"^([A-G])([#b]?)(?:(maj(?:or)?|min(?:or)?|m))?$",
    re.IGNORECASE,
)

# BPM + key inside parentheses: "(Em - 130bpm)" or "(D#m - 126bpm)"
_RE_PARENS = re.compile(
    r"\(\s*([A-G][#b]?(?:m|min|maj|minor|major)?)\s*[-–]\s*(\d{2,3})bpm\s*\)",
    re.IGNORECASE,
)

# ============================================================
# HELPERS
# ============================================================


def _split_camel(s: str) -> list[str]:
    """'ClosedHat' → ['Closed', 'Hat']; 'SynthBass' → ['Synth', 'Bass']."""
    return re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", s)


def _tokenize(name: str) -> list[str]:
    """Split on separators and CamelCase; return lowercase tokens."""
    raw = re.split(r"[_\-\s&+()]+", name)
    tokens: list[str] = []
    for part in raw:
        if not part:
            continue
        if re.search(r"[A-Z]", part) and re.search(r"[a-z]", part):
            tokens.extend(w.lower() for w in _split_camel(part) if w)
        else:
            tokens.append(part.lower())
    return tokens


def strip_lib(name: str, lib: str) -> str:
    if not lib:
        return name
    return re.sub(
        r"^" + re.escape(lib) + r"[_\-\s]?", "", name, flags=re.IGNORECASE
    )


def normalize_key(token: str) -> str | None:
    """Parse any key notation → compact '<NOTE>[m][#/b]' format."""
    m = _RE_KEY.fullmatch(token.strip())
    if not m:
        return None
    note = m.group(1).upper()
    accidental = m.group(2)        # '#', 'b', or ''
    mode_str = (m.group(3) or "").lower()
    is_minor = mode_str in ("m", "min", "minor")
    result = note + accidental
    if is_minor:
        result += "m"
    return result


def _file_specific_type(name: str, lib: str, folder_type: str) -> str | None:
    """Return a type from file name that differs from folder_type.

    Skips weak-type tokens (loop, drum, etc.) and tokens that produce
    the same abbreviation as the folder. Used to detect 'synth guitar' → GT
    when folder says SY.
    """
    clean = strip_lib(name, lib)
    tokens = _tokenize(clean)
    for tok in tokens:
        abbrev = AUTO_REPLACE.get(tok)
        if not abbrev or abbrev in WEAK_ABBREVS:
            continue
        if abbrev != folder_type:
            return abbrev
    return None


def detect_type(name: str, lib: str) -> str | None:
    """Return SHORT-TYPE from name, None if unknown."""
    clean = strip_lib(name, lib)
    tokens = _tokenize(clean)
    # Two passes: strong types first, weak types second.
    weak_result: str | None = None
    for tok in tokens:
        abbrev = AUTO_REPLACE.get(tok)
        if abbrev:
            if abbrev in WEAK_ABBREVS:
                if weak_result is None:
                    weak_result = abbrev
            else:
                return abbrev
    return weak_result


def detect_bpm_key_from_name(name: str, lib: str) -> tuple[int | None, str | None]:
    """Extract BPM and key from a single file/folder name."""
    clean = strip_lib(name, lib)

    # Parenthesised format first: "(Em - 130bpm)"
    pm = _RE_PARENS.search(name)
    if pm:
        key_raw, bpm_str = pm.group(1), pm.group(2)
        bpm_val = int(bpm_str)
        bpm = bpm_val if 50 <= bpm_val <= 200 else None
        key = normalize_key(key_raw)
        return bpm, key

    tokens = re.split(r"[_\-\s()]+", clean)
    bpm: int | None = None
    key: str | None = None

    for tok in tokens:
        # Explicit NNNbpm token
        m_bpm = re.fullmatch(r"(\d{2,3})bpm", tok, re.IGNORECASE)
        if m_bpm:
            v = int(m_bpm.group(1))
            if 50 <= v <= 200 and bpm is None:
                bpm = v
            continue
        # Plain number in BPM range
        if re.fullmatch(r"\d{2,3}", tok):
            v = int(tok)
            if 50 <= v <= 200 and bpm is None:
                bpm = v
            continue
        # Key token
        if key is None:
            key = normalize_key(tok)

    return bpm, key


def _user_ask(prompt: str, default: str | None = None) -> str:
    hint = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"  {prompt}{hint}: ").strip()
        if val:
            return val
        if default is not None:
            return default


# ============================================================
# STEP 0 — COPY
# ============================================================


def step0_copy(src: Path, dst: Path) -> None:
    if dst.exists():
        print(f"[SKIP] Destination already exists: {dst}")
        print("  Delete it first or choose a different DEST_PATH.")
        raise SystemExit(1)
    print(f"Copying .wav files\n  {src}\n→ {dst}")
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for dirpath, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        rel = Path(dirpath).relative_to(src)
        for fname in files:
            if Path(fname).suffix.lower() != ".wav":
                continue
            src_file = Path(dirpath) / fname
            dst_file = dst / rel / fname
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied += 1
    print(f"Copy done — {copied} .wav files.\n")


# ============================================================
# STEP 1 — STRIP LIBRARY PREFIX
# ============================================================


def _detect_prefix(root: Path) -> str:
    from collections import Counter

    def best_prefix(names: list[str]) -> str:
        """Find longest prefix (1–3 tokens) shared by ≥2/3 of names."""
        if len(names) < 2:
            return ""
        counts: Counter = Counter()
        for name in names:
            parts = [p for p in re.split(r"[_\-\s]", name) if p]
            prefix = ""
            for part in parts[:3]:
                prefix = f"{prefix}_{part}" if prefix else part
                counts[prefix] += 1
        threshold = max(2, len(names) * 2 // 3)
        valid = [p for p, cnt in counts.items() if cnt >= threshold]
        return max(valid, key=len) if valid else ""

    folders = [d for _, dirs, _ in os.walk(root) for d in dirs]
    prefix = best_prefix(folders)
    if prefix:
        return prefix

    stems = [
        Path(f).stem
        for _, _, files in os.walk(root)
        for f in files
        if Path(f).suffix.lower() in AUDIO_EXT
    ]
    return best_prefix(stems)


def _strip_prefix_from_all(root: Path, lib: str) -> None:
    """Rename every file and folder under root that starts with lib."""
    # Collect all paths bottom-up so we rename children before parents.
    all_paths: list[Path] = []
    for dirpath, dirs, files in os.walk(root, topdown=False):
        dp = Path(dirpath)
        for f in files:
            all_paths.append(dp / f)
        if dp != root:
            all_paths.append(dp)

    for path in all_paths:
        old_name = path.name
        if _ASD_RE.search(old_name):
            continue
        new_name = re.sub(
            r"^" + re.escape(lib) + r"[_\-\s]?", "", old_name, flags=re.IGNORECASE
        )
        if new_name and new_name != old_name:
            new_path = path.parent / new_name
            if not new_path.exists():
                path.rename(new_path)


def step1_strip_prefix(root: Path, lib: str) -> str:
    if not lib:
        detected = _detect_prefix(root)
        if detected:
            print(f"Detected library prefix: '{detected}'")
            ans = input("  Strip this prefix? [Y/n]: ").strip().lower()
            if ans != "n":
                lib = detected
            else:
                lib = input("  Enter prefix to remove: ").strip()
        else:
            print("No common prefix detected.")
            lib = input("  Enter prefix to remove (or leave blank to skip): ").strip()

    if lib:
        print(f"Stripping prefix '{lib}' from all names...")
        _strip_prefix_from_all(root, lib)
        print("Prefix stripped.\n")
    else:
        print("No prefix stripped.\n")
    return lib


# ============================================================
# STEP 2 — RENAME FILES
# ============================================================


def encode_suffix(bpm: int | None, key: str | None) -> str:
    """Build the +/-BPMKEY part of the filename."""
    if bpm is None and key is None:
        return ""
    if bpm is not None:
        if bpm >= 100:
            suffix = f"+{bpm - 100:02d}"
        else:
            suffix = f"-{bpm:02d}"
    else:
        suffix = "-"
    if key:
        suffix += key
    return suffix


def _ask_abbreviation(folder_name: str, token: str) -> str:
    abbrev = AUTO_REPLACE.get(token.lower())
    print(f"\n  Unknown type token '{token}' in folder '{folder_name}'")
    ans = _user_ask("Abbreviation (2 CAPS, or Enter to use default)", abbrev).upper()
    if len(ans) == 2 and ans.isalpha():
        AUTO_REPLACE[token.lower()] = ans
        return ans
    return ans[:2].upper() if ans else "XX"


def _get_folder_type(folder: Path, lib: str) -> str | None:
    """Determine SHORT-TYPE by scanning folder name (leaf first)."""
    t = detect_type(folder.name, lib)
    if t:
        return t
    # Walk up one more level (grandparent) for nested structures.
    if folder.parent != folder:
        t = detect_type(folder.parent.name, lib)
        if t and t not in WEAK_ABBREVS:
            return t
    return None


def rename_folder(folder: Path, lib: str) -> None:
    audio = sorted(
        f for f in folder.iterdir()
        if f.is_file()
        and f.suffix.lower() in AUDIO_EXT
        and not _ASD_RE.search(f.name)
    )
    if not audio:
        return

    # Determine folder-level type.
    folder_type = _get_folder_type(folder, lib)

    # Extract BPM / key from folder name (for packs where folder carries this info).
    folder_bpm, folder_key = detect_bpm_key_from_name(folder.name, lib)

    # Counter: per-type sequential number within this folder.
    counters: dict[str, int] = {}

    # We may need to ask the user for unknown types — ask once per token.
    asked: dict[str, str] = {}

    for f in audio:
        bpm, key = detect_bpm_key_from_name(f.stem, lib)
        bpm = bpm if bpm is not None else folder_bpm
        key = key if key is not None else folder_key

        # Determine type: folder gives the default category; file name can
        # override with a more specific instrument type (e.g. SY folder but
        # file contains 'guitar' → GT).
        if folder_type is not None:
            specific = _file_specific_type(f.stem, lib, folder_type)
            short_type = specific if specific else folder_type
        else:
            short_type = detect_type(f.stem, lib)

        # If still unknown, ask user.
        if short_type is None:
            # Find first unrecognised token as candidate label.
            tokens = _tokenize(strip_lib(folder.name or f.stem, lib))
            label = next((t for t in tokens if t and not t.isdigit()), f.stem)
            if label in asked:
                short_type = asked[label]
            else:
                short_type = _ask_abbreviation(folder.name, label)
                asked[label] = short_type

        counters[short_type] = counters.get(short_type, 0) + 1
        n = counters[short_type]

        suffix = encode_suffix(bpm, key)
        new_stem = f"{short_type}{n}{suffix}"
        new_name = new_stem + f.suffix.lower()
        new_path = f.parent / new_name

        if f == new_path or (f.name == new_name):
            continue
        if new_path.exists():
            print(f"  [SKIP] exists: {new_name}")
            continue
        print(f"  {f.name}  →  {new_name}")
        f.rename(new_path)


def step2_rename(root: Path, lib: str) -> None:
    print("=== Step 2: renaming audio files ===\n")
    for dirpath, dirs, files in os.walk(root):
        # Skip hidden folders.
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        folder = Path(dirpath)
        audio_here = [
            f for f in files
            if Path(f).suffix.lower() in AUDIO_EXT
            and not _ASD_RE.search(f)
        ]
        if not audio_here:
            continue
        print(f"\n[Folder] {folder.relative_to(root)}")
        rename_folder(folder, lib)
    print("\n=== Done. ===")


# ============================================================
# MAIN
# ============================================================


def main() -> None:
    src = Path(SOURCE_PATH)
    dst = Path(DEST_PATH)

    if not src.is_dir():
        print(f"ERROR: SOURCE_PATH not found: {src}")
        raise SystemExit(1)

    # Step 0
    step0_copy(src, dst)

    # Step 1
    lib = LIBRARY_NAME
    lib = step1_strip_prefix(dst, lib)

    # Step 2
    step2_rename(dst, lib)


if __name__ == "__main__":
    main()
