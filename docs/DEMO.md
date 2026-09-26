# ⚽ Hackathon Demo Script (2 Minutes)

A step-by-step guide for presenting **Football Highlight Studio** live to judges.

---

## ⏱️ The 2-Minute Presentation Flow

### 0:00 – 0:25: The Problem & The Solution
> *"Broadcasters and creators spend hours scrubbing through 90-minute recordings to find key match moments. Computer vision models are slow, expensive, and require dedicated GPUs. Football Highlight Studio uses transparent, lightweight audio excitement detection to find crowd roars in seconds."*

- Open the home page (`http://localhost:5173` or deployed URL).
- Point out the clean interface, dark mode toggle, and the **"Instant Demo"** banner.

### 0:25 – 0:45: Instant Demo Mode
> *"Judges don't have time to wait for a 4 GB upload. We built an instant pre-processed demo mode."*

- Click **"Try with a sample match"**.
- Instantly opens the 12-minute synthetic broadcast (`/jobs/demo-match`).
- Show the scrubbable **Timeline**: acoustic excitement envelope, rolling 90s baseline curve, and detected moments highlighted in primary green.
- Play the video in the player and click on a moment card or timeline peak to seek directly to the build-up.

### 0:45 – 1:15: Editorial Studio & Recovering Missed Moments
> *"Audio detection is fast, but it can miss subtle chances. We give creators full editorial recovery tools."*

1. **Sub-Threshold Suggestions:** Open the **"Possible Moments"** accordion. Show the dashed candidate peaks detected slightly below default thresholds. Click **"Add"** on one candidate to instantly promote it into the highlight reel.
2. **Manual Moment Creation:** Click **"Add Moment"** or double-click anywhere on the timeline to create a new manual window (`source="manual"`).
3. **Trimming & Exclusion:** Drag the edges of a moment to trim lead-in or celebration time, or toggle the include/exclude switch to drop a false alarm.

### 1:15 – 1:35: 3-Second Retuning & Multi-Version Rendering
> *"Notice that retuning never re-extracts audio."*

1. Open **Tuning Controls** and adjust sensitivity or length cap.
2. Click **Apply Changes**: show the log drawer — detection completes in under **1.5 seconds**!
3. Click **Render Reel**: cuts exactly the selected, trimmed moments and inserts smooth 0.25-second video and audio fade transitions.
4. Show the **Version History**: compare current render against previous versions.

### 1:35 – 2:00: Downloads, Honest Limits & Summary
1. Open the **Downloads** menu: demonstrate downloading `highlights.mp4`, timestamped `windows.json` / `windows.csv` manifests, and the acoustic analysis plot (`debug.png`).
2. Conclude with an honest summary:
   > *"Because this uses audio acoustics rather than visual ball-tracking, it's honest about its limits: it tracks crowd excitement, not soccer rules. But it's fast, runs on any basic CPU, and gives the human creator complete control."*

---

## 🎬 How Demo Media Was Generated

To respect copyright and ensure 100% legal, reproducible judge demonstrations, all demo files are generated synthetically:

### 1. 12-Minute Synthetic Match (`synthetic_match.mp4`)
Generated with `tools/make_synthetic_match.py`:
```bash
python tools/make_synthetic_match.py \
  --wav tools/synthetic_match.wav \
  --mp4 "raw videos/synthetic_match.mp4" \
  --events-json tools/synthetic_events.json \
  --events-csv tools/synthetic_events.csv \
  --duration 720
```
- **Duration:** 720 seconds (12 minutes).
- **Acoustic Profile:** Pink noise ambient crowd hum with synthetic commentary bursts and 5 distinct ground-truth crowd roars:
  - 01:35 – Roar 1 (+10 dB, 8s sustain)
  - 03:30 – Roar 2 (+7 dB, 5s sustain)
  - 05:45 – Roar 3 (+12 dB, 10s sustain)
  - 08:10 – Roar 4 (+6 dB, 4s sustain)
  - 10:20 – Roar 5 (+11 dB, 9s sustain)
- **Distractors:** Injected referee whistles (3 kHz pure tone), microphone thump (low-frequency transient), and pre-match intro jingle to test transient rejection.

### 2. 60-Second Sample Clip (`short_match_60s.mp4`)
A 60-second version (805 KB) created for fast pipeline runs (completes in ~2 seconds):
```bash
python tools/make_synthetic_match.py \
  --wav tools/short_match_60s.wav \
  --mp4 "raw videos/short_match_60s.mp4" \
  --duration 60
```
Available via one-click download at `/api/sample/clip` or the "Get 60s Clip" button on the home page.
