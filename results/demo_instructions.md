# Recording results/demo.mp4 (QuickTime, no ffmpeg)

Target: about 80 seconds, no audio, captions burned in. The captions are an
overlay you advance with a key while recording, so no editing is needed
afterwards.

## What the demo will show

Checked against the running API with the "Overnight fine-tune" preset. The text
says "It's 7pm now", so these numbers do not depend on when you record, only on
the season (SON until Nov 30) and the preset's 6 h duration:

| basis | badge | best start | carbon | withdrawal | consumption |
|---|---|---|---|---|---|
| average | CONFLICT | 1 AM | +5.5 % | −14.6 % | −8.0 % |
| marginal-empirical | ALIGNED | 8 PM | +9.9 % | +24.7 % | +25.0 % |

The explanation came back verified in about 2 s.

## 1. Set up (once, before recording)

1. Make sure the FastAPI app is running:
   `python3 -m uvicorn api:app --port 8600` from `~/thirst`.
2. In Chrome, open `http://localhost:8600`. Hide the bookmarks bar
   (⌘⇧B). Size the window to about 1440×900. Turn on Do Not Disturb.
3. **Warm up once.** Click **Overnight fine-tune**, then **Place it**, and wait
   for the explanation. This wakes the Nemotron endpoint so the recorded run
   isn't slow. Then reload the page (⌘R).
4. **Add the captions.** Open DevTools (⌥⌘J), go to the Console, and paste the
   snippet below. Chrome may ask you to type `allow pasting` first. Close
   DevTools. The overlay survives closing DevTools but not a page reload.
   - `]` shows the next caption; `[` goes back.
   - Keys are ignored while the cursor is in the text box.

```js
(() => {
  const caps = [
    "GridShift: schedule compute when the PJM grid is less thirsty",
    "A job in plain English. Nemotron quotes the deadline; Python computes the 12-hour window.",
    "Average basis: the lowest-carbon start saves 5.5 % carbon but uses 14.6 % more water withdrawal.",
    "Marginal-empirical basis: same job, all three improve. The conflict depends on the accounting basis.",
    "Nemotron explains. verify() checks every number against Python's record, sign included.",
    "If the job can move regions: water stress reorders them (consumption, average basis).",
    "Evidence: classifier accuracy vs its baseline, explanation fidelity. Holdout still sealed.",
  ];
  let i = -1;
  const el = document.createElement("div");
  Object.assign(el.style, {
    position: "fixed", left: "50%", bottom: "28px", transform: "translateX(-50%)",
    maxWidth: "80vw", padding: "12px 22px", background: "rgba(0,0,0,.85)", color: "#fff",
    font: "600 20px/1.35 -apple-system, system-ui, sans-serif", borderRadius: "10px",
    textAlign: "center", zIndex: 2147483647, pointerEvents: "none",
    transition: "opacity .25s", opacity: 0,
  });
  document.body.appendChild(el);
  const show = () => { el.style.opacity = i < 0 ? 0 : 1; if (i >= 0) el.textContent = caps[i]; };
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("textarea, input[type=text], input[type=number]")) return;
    if (e.key === "]") { i = Math.min(i + 1, caps.length - 1); show(); }
    if (e.key === "[") { i = Math.max(i - 1, -1); show(); }
  });
})();
```

## 2. Record

1. Press ⌘⇧5 and choose **Record Selected Portion**. Drag the box around the
   Chrome window.
2. Under **Options**:
   - Microphone: **None**.
   - **Show Mouse Clicks**: on.
   - Save to: **Other Location…** → `~/thirst/results`.
3. Click **Record**, then follow the beats below. Click inside the page first
   (not in the text box) so `]` reaches it.

| time | do this | press |
|---|---|---|
| 0:00 | Hold on the empty page. | `]` caption 1 |
| 0:05 | Click **Overnight fine-tune**, then **Place it**. Wait for the classification panel: `deferable`, "by 7am tomorrow", 12 h. Click an empty area so the text box loses focus. | `]` caption 2 |
| 0:17 | The red **CONFLICT** badge appears, with carbon and water bars on opposite sides. Hold. | `]` caption 3 |
| 0:29 | Under accounting basis, click **marginal-empirical**. The bars swing to **ALIGNED**. Hold. | `]` caption 4 |
| 0:41 | Click **Explain with Nemotron** (about 2 s). Hold on the headline, the body, and the green "Nemotron · verified" line starting "verify(): every number traced to Python". | `]` caption 5 |
| 0:55 | Under location, click **Portable**. Scroll down to the region table and the slope chart. Hold. | `]` caption 6 |
| 1:08 | Scroll to the **Evidence** panel. Hold. | `]` caption 7 |
| 1:18 | Hold, then stop recording: ⌘⌃⎋, or the stop button in the menu bar. | |

If a beat goes wrong, stop, reload, paste the snippet again and re-record.
Retakes are cheap.

## 3. Convert to MP4

QuickTime saves `Screen Recording <date>.mov`. Rename it to `demo.mov`, then:

```bash
cd ~/thirst/results
avconvert -s demo.mov -o demo.mp4 -p Preset1920x1080 --replace --progress
# trim dead air at either end if needed, e.g.: --start 1.5 --duration 80
```

`avconvert` ships with macOS. The `.mp4` extension selects the container, and
`Preset1920x1080` gives H.264 at 1080p. Check the result with
`open demo.mp4`, then delete `demo.mov` if it's too large to keep.
