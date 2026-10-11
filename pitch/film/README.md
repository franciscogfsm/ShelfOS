# ShelfOS — demo film

Everything needed to rebuild the demo film: the edit, the renderer, the soundtrack generator and the
screenshots it is made of. There are two cuts, 30 s and 45 s. The rendered `.mp4` files are not in the
repository (git-ignored here: the 4K render is over GitHub's 100 MB limit per file); `node render.mjs`
writes them into this folder.

Every picture in the film is a real screenshot of the running app (3840 × 2160 for the desktop,
1290 × 2796 for the mobile page). Nothing in the UI is redrawn: the film only moves a camera over those
screenshots, cuts from one real state to the next when a control is tapped, and adds the tap marker, the
feature label and the closing wordmark (itself cropped from the app).

The numbers on screen are whatever the app showed at capture time; they are not official evaluation results.

## What is here

| File | What it is |
|---|---|
| `film.html`, `film45.html` | The edit of each cut: camera moves (`deskCam`), cuts (`CUTS`), taps (`TAPS`), labels (`LABELS`). Open one in a browser to play it live; click once for sound. |
| `shots/`, `shots45/` | The screenshots of each cut, plus `meta*.json` with the position of the controls at capture time. |
| `capture.mjs` | Takes the screenshots from the running app. |
| `render.mjs` | Renders a cut frame by frame in headless Chrome and encodes it with ffmpeg. |
| `audio.py`, `audio45.py` | Synthesise the soundtrack (120 BPM, so every tap lands on a beat); no third-party music. |
| `cues.json`, `cues45.json` | Tap and effect times, written by `render.mjs` and read by the audio scripts. |
| `sound.wav`, `sound45.wav` | The soundtracks as rendered. `python audio.py` / `python audio45.py` rebuild them. |

## Rebuild

Needs Node, Chrome, ffmpeg on PATH, and Python with NumPy for the soundtrack. If Chrome is not in
`C:/Program Files/Google/Chrome/Application/chrome.exe`, set `CHROME` to its path.

```powershell
cd pitch/film
npm install

# 45 s cut
$env:FILM = '45'
node render.mjs               # writes ShelfOS-film-45s.mp4, 1920 x 1080 at 60 fps (about 5 min)
$env:SCALE = '2'
node render.mjs               # writes ShelfOS-film-45s-4k.mp4, 3840 x 2160 (about 12 min)

# 30 s cut
Remove-Item Env:FILM, Env:SCALE
node render.mjs               # writes ShelfOS-film-30s.mp4 (about 3 min)
```

The 4K render needs roughly 3 GB of free RAM; with less, the machine starts swapping.

`node render.mjs stills 12 20.5` writes single frames at those seconds to `stills<FILM>/`, and
`node render.mjs sheet` writes sixty evenly spaced frames, for a quick check of an edit.

After changing a tap or an effect time in the edit, rebuild the soundtrack before rendering:

```powershell
node render.mjs stills 0      # rewrites cues.json (cues45.json with FILM=45)
python audio.py               # or: python audio45.py
```

## Retake the screenshots

Only needed when the app changes. The app must be running; `SHELFOS_URL` is its address (default
`http://localhost:3210`, the dev server) and `SHOTS` the folder to write (default `shots`).

```powershell
$env:SHOTS = 'shots45'
node capture.mjs wall         # one group per call
```

| Cut | Groups it needs |
|---|---|
| 30 s (`shots`) | `wall`, `lapse`, `camera`, `tasks`, `analytics`, `run`, `search`, `ai`, `light`, `staff`, `brand` |
| 45 s (`shots45`) | `wall`, `lapse`, `camera`, `tasks`, `analytics`, `run`, `search`, `type`, `ai2`, `light`, `staff`, `stafflight`, `brand` |

Run each group in its own call. The `light` group switches the app to the light theme, and the theme
carries over to whatever is captured next in the same call.

Two things in the edits depend on what was captured:

- The control positions (`NAV`, `TAPS`) are copied from `meta*.json`. If the layout of the app changes,
  update them after retaking the screenshots.
- `ai2` sends a real question to the assistant and takes a frame every 380 ms until the answer is complete,
  so the number of `ai_NN` frames changes with the response time. `film45.html` plays `ai_00` to `ai_10`
  (`THINK`); adjust it to the frames you get.

## The two cuts

### 45 s

Its own screenshots (`shots45/`, taken after the model was retrained, so its numbers differ from the
30 s cut) and a soundtrack with sound effects.

| Time | Feature | What is tapped |
|---|---|---|
| 0.0 – 6.0 | Opening line, then the store wall | — |
| 6.0 – 10.0 | Day replay, 07:35 to 23:35 | Play |
| 10.0 – 15.5 | Camera view, planogram slots, area detail | Camera 6215, "Banana · slot 2", "Show what ShelfOS sees as product" |
| 15.5 – 20.0 | Tasks | Tasks, three tasks ticked (62 to 59, store score 74 % to 76 %) |
| 20.0 – 25.5 | Analytics, framed wide | Analytics, Stock, Compliant, Covered |
| 25.5 – 28.0 | Test images | Test images, Download predictions.json |
| 28.0 – 30.5 | Search, typed letter by letter | Search |
| 30.5 – 36.0 | ShelfOS AI | Assistant, "What needs attention first?", the "Banana" card in the answer (opens camera 6215, slot 2) |
| 36.0 – 41.7 | Team mobile (`/colaboradores`) | Phone icon, "Já estou aqui" (simulated confirmation, as labelled in the app) |
| 41.7 – 45.0 | Light theme, closing wordmark | Theme switch |

The assistant exchange is real: the question was sent to the running app and the screenshots are its
"thinking" state and the answer it gave. The only edit is time: the wait for the answer (about 4.5 s when
captured) is shown in about 1.5 s.

### 30 s

| Time | Feature | What is tapped |
|---|---|---|
| 0.0 – 4.0 | Opening line, then the store wall | — |
| 4.0 – 6.0 | Day replay, 07:35 to 23:35 | Play |
| 6.0 – 10.0 | Camera view, planogram slots, area detail | Camera 6215, "Banana · slot 2", "Show what ShelfOS sees as product" |
| 10.0 – 13.0 | Tasks | Tasks, three tasks ticked (62 to 59, store score 71 % to 73 %) |
| 13.0 – 16.5 | Analytics | Analytics, Stock, Compliant, Covered |
| 16.5 – 18.5 | Test images | Test images, Download predictions.json |
| 18.5 – 20.0 | Search | Search, query "banana" |
| 20.0 – 21.5 | Assistant | Assistant |
| 21.5 – 26.5 | Team mobile (`/colaboradores`) | Phone icon, "Já estou aqui" |
| 26.5 – 30.0 | Light theme, closing wordmark | Theme switch |
