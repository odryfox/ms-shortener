# Sample name shortener for Elektron Model:Samples.

- Step 0: recursively copy SOURCE_PATH → DEST_PATH (original untouched).
- Step 1: detect & strip library prefix from all folder/file names.
- Step 2: rename audio files to <TYPE><N>+/-<BPM><KEY>.ext

### Output format examples:
  - KK1.wav
  - KK12.wav
  - PD16-Cm#.wav
  - PD16-60Cm#.wav (60bpm)
  - PD16+60Cm#.wav (160bpm)
  - SH2+22.wav (122bpm)
  - HH1.wav

Set SOURCE_PATH and DEST_PATH below, then run: python3 main.py
