#!/usr/bin/env python3
"""Generate the voice-over for the demo from the narration script in record_demo.py.

    python3 -I scripts/narrate.py                 # default voice
    ATLAS_VOICE=Samantha python3 -I scripts/narrate.py
    ATLAS_VOICE=Rishi ATLAS_RATE=180 python3 -I scripts/narrate.py

Uses macOS's built-in speech synthesis, so it costs nothing and needs no account.
These are system voices: clear and clearly synthetic. For the final submission,
recording your own voice over the same script will sound better than any of them —
the script is in TEAM/demo-script.md and the lines below are the same text.

Writes demo/narration/<key>.wav plus script.json, which record_demo.py reads to pace
the video to the voice and to lay the audio back at the right moments.
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from record_demo import NARRATION, OUT                      # single source of truth

VOICE = os.environ.get("ATLAS_VOICE", "Daniel")
RATE  = os.environ.get("ATLAS_RATE", "178")
DIR   = os.path.join(OUT, "narration")


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    try: return round(float(r.stdout.strip()), 3)
    except ValueError: return 0.0


def main():
    voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    if VOICE not in voices:
        sys.exit(f"voice {VOICE!r} is not installed. `say -v '?'` lists what is.")

    os.makedirs(DIR, exist_ok=True)
    lines, total = [], 0.0
    print(f"  voice {VOICE} at {RATE} wpm -> {DIR}")
    for key, _scene, text in NARRATION:
        wav = os.path.join(DIR, f"{key}.wav")
        subprocess.run(["say", "-v", VOICE, "-r", RATE,
                        "--file-format=WAVE", "--data-format=LEI16@22050",
                        "-o", wav, text], check=True)
        # Trim the dead air the synthesiser leaves on each end so lines land tightly.
        trimmed = wav + ".t.wav"
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af",
                            "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB:"
                            "detection=peak,areverse,"
                            "silenceremove=start_periods=1:start_silence=0.12:start_threshold=-45dB:"
                            "detection=peak,areverse", trimmed], capture_output=True)
        if r.returncode == 0 and os.path.getsize(trimmed) > 2000:
            os.replace(trimmed, wav)
        elif os.path.exists(trimmed):
            os.remove(trimmed)

        d = duration(wav)
        total += d
        lines.append({"key": key, "text": text, "wav": wav, "duration": d,
                      "words": len(text.split())})
        print(f"    {key:<10} {d:5.1f}s  {len(text.split()):3} words")

    json.dump({"voice": VOICE, "rate": RATE, "total": round(total, 1), "lines": lines},
              open(os.path.join(DIR, "script.json"), "w"), indent=1)
    print(f"\n  {len(lines)} lines, {total:.0f}s of speech")
    print(f"  wrote {os.path.join(DIR, 'script.json')}")
    print("  now run: python3 -I scripts/record_demo.py")


if __name__ == "__main__":
    main()
