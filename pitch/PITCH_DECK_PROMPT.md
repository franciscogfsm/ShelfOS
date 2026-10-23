# Prompt: build the ShelfOS pitch deck as one HTML page

Attach to this prompt: the four screenshots of the app (intro screen, store wall in light
mode, store wall in dark mode, the navigation pill). They are the visual reference.

---

## What I need

Build our hackathon pitch deck as a single `index.html`: a scroll-driven presentation, one
full-screen slide per section, that we will show on a projector to the judges of JunctionX
Lisbon 2026 and present live in about three minutes.

The product is **ShelfOS**, our entry for the Sensei challenge "Fresh eyes on fresh
produce": ceiling cameras in an autonomous store look at the fruit and vegetable section,
and for every area of the planogram the system has to say whether the right product is
there and how full it is (empty, half, full).

The deck has to look like it is part of the product. Our app is minimal, near-black,
with "liquid glass" surfaces, and it has a light mode. The deck uses exactly the same
visual language, and has the same light/dark switch. The judges see the app right after
the deck, and the two should feel like one thing.

The quality bar is a keynote from a design-led company: very few words per slide, large
type, a lot of empty space, and motion that is smooth and deliberate. If a slide feels
busy, remove things. I would rather have twelve calm slides than eight crowded ones.

## How it will be used

- Projected at 1920x1080, in Chrome, full screen, offline. It must also hold up on a
  laptop at 1440x900.
- One person scrolls or presses keys while another talks. So each slide must make its
  point in a glance: a headline, one visual, at most three short supporting lines.
- No build step and no network: one `index.html` with CSS and JavaScript inline. No
  libraries, no CDN, no web fonts loaded from the internet. Use the font stack
  `"Geist", "Inter", system-ui, -apple-system, "Segoe UI", sans-serif` and
  `"Geist Mono", ui-monospace, "SF Mono", Consolas, monospace` for small labels and numbers.
- Images are optional files next to the page: `assets/wall-dark.png`,
  `assets/wall-light.png`, `assets/camera.png`, `assets/analytics.png`,
  `assets/tasks.png`, `assets/test-images.png`. Show the dark or light one according to
  the theme. If a file is missing the slide must still look finished, so draw a glass
  placeholder frame behind every image.

## Navigation and behaviour

- Vertical scroll with scroll snapping, one slide per viewport (`100dvh`).
- Keys: arrow down, arrow right, space and page down go forward; arrow up, arrow left and
  page up go back; home and end jump; `T` switches theme; `F` toggles full screen.
- A floating glass pill, top centre, like the app's navigation: the wordmark on the left,
  the section names in the middle with the current one highlighted (same pressed style
  as the app), the theme switch on the right. It hides on the intro slide and fades in
  after it.
- A thin progress line and a slide counter in mono type (`03 / 12`) in a corner.
- Each slide animates when it enters the viewport (IntersectionObserver), once per visit
  forwards, and stays put. Nothing loops forever except very quiet ambient effects.
- Respect `prefers-reduced-motion`: everything is simply visible, no movement.
- No visible scrollbars.

## The design system (copy these values exactly)

These come straight from the app's stylesheet. The whole deck draws with the variables,
so the theme switch only swaps the first block. Set the theme with
`<html data-theme="light">`; dark is the default.

```css
:root {
  color-scheme: dark;
  --fg: 255 255 255; --k: 1; --shade: 1; --hi: 1;
  --bg: #09090b; --well: #101012; --pit: #000; --pitc: 0 0 0; --panel: 20 20 23;
  --ink: #fafafa; --ink-2: #e4e4e7; --ink-3: #d4d4d8; --muted: #a1a1aa; --dim: #71717a; --faint: #52525b;
  --ease-out: cubic-bezier(.16, 1, .3, 1); --ease-spring: cubic-bezier(.34, 1.4, .64, 1);
}
:root[data-theme="light"] {
  color-scheme: light;
  --fg: 9 9 11; --k: 1.35; --shade: .2; --hi: 6;
  --bg: #f3f3f5; --well: #e6e6ea; --pit: #ececef; --pitc: 255 255 255; --panel: 255 255 255;
  --ink: #09090b; --ink-2: #27272a; --ink-3: #3f3f46; --muted: #5b5b64; --dim: #85858e; --faint: #b4b4bb;
}

/* page background: three very faint lights on near-black */
.app-shell {
  background:
    radial-gradient(60% 50% at 18% -8%, rgb(var(--fg) / calc(.071 * var(--k))), transparent 70%),
    radial-gradient(45% 40% at 96% 4%, rgb(var(--fg) / calc(.039 * var(--k))), transparent 70%),
    radial-gradient(50% 45% at 60% 110%, rgb(var(--fg) / calc(.031 * var(--k))), transparent 70%),
    var(--bg);
}

/* floating controls (the navigation pill, chips) */
.glass {
  border: 1px solid rgb(var(--fg) / calc(.102 * var(--k)));
  background: linear-gradient(180deg, rgb(var(--fg) / calc(.09 * var(--k))), rgb(var(--fg) / calc(.031 * var(--k))) 50%, rgb(var(--fg) / calc(.051 * var(--k))));
  box-shadow: inset 0 1px 0 rgb(255 255 255 / calc(.18 * var(--hi))), inset 0 -1px 0 rgb(0 0 0 / calc(.302 * var(--shade))), 0 16px 40px -18px rgb(0 0 0 / calc(.8 * var(--shade)));
  backdrop-filter: blur(22px) saturate(170%);
}
:root[data-theme="light"] .glass { border-color: #09090b12; background: linear-gradient(180deg, #ffffffe6, #ffffffa6); box-shadow: inset 0 1px 0 #fff, 0 14px 34px -20px #09090b47; }

/* navigation pill and its buttons */
.main-nav { display: flex; gap: 2px; padding: 5px; border-radius: 999px; }
.nav-item { display: flex; align-items: center; gap: 9px; min-height: 40px; padding: 0 18px; border: 1px solid transparent; border-radius: 999px; font-size: 13px; font-weight: 500; color: var(--muted); transition: background-color 240ms, color 240ms, border-color 240ms, box-shadow 240ms, transform 180ms; }
.nav-item:hover { color: var(--ink); background: rgb(var(--fg) / calc(.051 * var(--k))); }
.nav-item:active { transform: scale(.97); }
.nav-item[aria-pressed="true"] { color: var(--ink); border-color: rgb(var(--fg) / calc(.18 * var(--k))); background: linear-gradient(180deg, rgb(var(--fg) / calc(.18 * var(--k))), rgb(var(--fg) / calc(.071 * var(--k)))); box-shadow: inset 0 1px 0 rgb(255 255 255 / calc(.278 * var(--hi))), 0 6px 16px -8px rgb(0 0 0 / calc(.702 * var(--shade))); }

/* plain panels on the page */
.glass-card {
  border: 1px solid rgb(var(--fg) / calc(.078 * var(--k))); border-radius: 20px;
  background: linear-gradient(160deg, rgb(var(--fg) / calc(.059 * var(--k))), rgb(var(--fg) / calc(.02 * var(--k))) 45%, rgb(var(--fg) / calc(.031 * var(--k))));
  box-shadow: inset 0 1px 0 rgb(255 255 255 / calc(.102 * var(--hi))), 0 20px 44px -28px rgb(0 0 0 / calc(.902 * var(--shade)));
}
:root[data-theme="light"] .glass-card { border-color: #09090b12; background: linear-gradient(160deg, #fff, #ffffffb8); box-shadow: inset 0 1px 0 #fff, 0 1px 2px #09090b0a, 0 22px 44px -32px #09090b40; }

/* liquid glass: the hero surface. --tone is the card's own colour, pooling at the bottom corner */
.metric-card {
  --tone: var(--ink);
  position: relative; overflow: hidden; padding: 20px; border: 0; border-radius: 26px; isolation: isolate;
  background:
    radial-gradient(110% 80% at 0% 0%, rgb(255 255 255 / .13), transparent 58%),
    radial-gradient(95% 75% at 88% 118%, color-mix(in srgb, var(--tone) 26%, transparent), transparent 72%),
    linear-gradient(165deg, rgb(255 255 255 / .075), rgb(255 255 255 / .018) 55%, rgb(255 255 255 / .04));
  backdrop-filter: blur(28px) saturate(190%);
  box-shadow: inset 0 1px 1px rgb(255 255 255 / .22), inset 0 -10px 22px -14px rgb(255 255 255 / .12), inset 0 0 0 1px rgb(255 255 255 / .03), 0 26px 50px -30px #000, 0 22px 44px -30px color-mix(in srgb, var(--tone) 45%, transparent);
  transition: transform 450ms var(--ease-out), box-shadow 450ms;
}
/* the bright rim */
.metric-card::before { content: ""; position: absolute; z-index: 1; inset: 0; padding: 1px; border-radius: inherit; pointer-events: none; background: linear-gradient(135deg, rgb(255 255 255 / .75), rgb(255 255 255 / .1) 26%, rgb(255 255 255 / .04) 62%, color-mix(in srgb, var(--tone) 70%, #fff 10%)); -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask: linear-gradient(#000 0 0) content-box exclude, linear-gradient(#000 0 0); opacity: .8; }
/* a band of light that crosses the slab on hover */
.metric-card::after { content: ""; position: absolute; z-index: 1; top: -20%; bottom: -20%; left: 0; width: 45%; pointer-events: none; background: linear-gradient(100deg, transparent, rgb(255 255 255 / .16) 45%, rgb(255 255 255 / .04) 60%, transparent); translate: -140% 0; rotate: 8deg; }
.metric-card:hover { transform: translateY(-4px) scale(1.012); }
.metric-card:hover::after { translate: 340% 0; transition: translate 1100ms var(--ease-out); }
:root[data-theme="light"] .metric-card {
  background:
    radial-gradient(110% 80% at 0% 0%, #fff, transparent 60%),
    radial-gradient(95% 75% at 88% 118%, color-mix(in srgb, var(--tone) 20%, transparent), transparent 72%),
    linear-gradient(165deg, #ffffffc7, #ffffff66 55%, #ffffff99);
  box-shadow: inset 0 1px 1px #fff, inset 0 -12px 24px -14px #fff, 0 1px 2px #09090b0d, 0 26px 50px -32px #09090b52, 0 22px 44px -28px color-mix(in srgb, var(--tone) 55%, transparent);
}
:root[data-theme="light"] .metric-card::before { background: linear-gradient(135deg, #fff, #09090b14 30%, #09090b0d 62%, color-mix(in srgb, var(--tone) 75%, #fff)); opacity: 1; }
:root[data-theme="light"] .metric-card::after { background: linear-gradient(100deg, transparent, #ffffffd9 45%, #ffffff40 60%, transparent); }
```

Type and colour rules, also from the app:

- Wordmark: `Shelf` in weight 300 to 400 and `OS` in weight 800, letter-spacing `-.055em`,
  both in `--ink` (see the intro screenshot).
- Headlines: weight 600, letter-spacing `-.05em`, line-height 1.1. The second half of a
  headline is in `--dim`, as in "Every shelf. **In sight.**" on the store wall.
- Eyebrow labels: 10 to 12 px, uppercase, letter-spacing `.16em`, colour `--dim`, mono.
- Big numbers: weight 600, letter-spacing `-.06em`.
- Colour is reserved for shelf states and nothing else. Empty `#ff6b7a`, wrong product
  `#a996ff`, running low `#f5b84a`. Fine is plain `--ink` (white in dark, black in
  light). Everything else is neutral. No gradients of colour, no blue, no emoji.
- Corners: 26 px for liquid glass, 20 px for panels, 999 px for pills and buttons.

## Motion

- Easing `--ease-out` for almost everything, 500 to 1100 ms. Elements arrive with a small
  rise (10 to 16 px), a fade, and a slight blur clearing (`filter: blur(6px)` to 0).
  Stagger siblings by 60 to 90 ms.
- Numbers count up when their slide arrives, with tabular figures.
- Lines draw themselves (SVG `stroke-dashoffset`), rings sweep, sparklines wipe in from
  the left.
- Liquid glass cards tilt a few degrees towards the pointer and the light band crosses
  them. Keep it subtle.
- Only animate `transform`, `opacity`, `filter` and stroke properties, so it stays at
  60 fps on a laptop driving a projector.

### The intro (the most important ten seconds)

Pure black screen. Reproduce the attached intro screenshot and bring it to life:

1. A single thin vertical line draws down the centre of the screen.
2. A small glass pill fades in above with the eyebrow `SHELF INTELLIGENCE`.
3. The wordmark `ShelfOS` resolves letter by letter out of blur, very large (about 14vw),
   `Shelf` light and `OS` heavy. As `OS` lands, a soft light sweeps once across the word.
4. Under it, one line fades in: `Every shelf. In sight.` with the second half dimmed.
5. Faintly, behind everything, the outlines of planogram areas (thin quadrilaterals in
   the three state colours at very low opacity) drift into place like a shelf seen from
   the ceiling, then settle. This must stay almost subliminal.
6. The thin line becomes the scroll hint and pulses slowly.

On first scroll the wordmark shrinks and travels to the top-left of the navigation pill,
which fades in around it.

## The slides

Write the copy in English. Keep my wording where I give it; tighten where I describe.

**1. Intro.** As above.

**2. The problem.** Headline: `Fresh produce is the hardest shelf to see.`
Three short lines that appear one at a time, each with its state colour dot:
- Empty gondola: lost sales. (red)
- Wrong product in the wrong place: wrong prices, confused customers. (purple)
- Running low, unnoticed: staff walking the store to check. (amber)
Small footnote: loose products, no barcode, piled, hidden by hands.

**3. The challenge.** Headline: `One real day. No labels.`
Count-up figures in four liquid glass cards: `14` ceiling cameras, `181` images,
`153` planogram areas, `94` products. Underline: Continente Bom Dia S. Romão, Leiria,
an autonomous store powered by Sensei. Then the scoring rule as a small table that
slides in, because it drives our design:
right product `+1`, wrong `-2`; right stock `+1`, too low `-2`, too high `-3`.

**4. Our answer.** Headline: `ShelfOS turns every camera frame into a to-do list.`
The hero screenshot of the store wall (`assets/wall-dark.png` / `wall-light.png`) inside
a glass frame, rising in with a slow parallax as the slide scrolls. Three words under
it: `See. Decide. Act.`

**5. How it works (the architecture diagram).** Headline: `A frozen eye. A small brain. A long memory.`
This is the centrepiece: an animated diagram drawn in SVG and glass nodes, built step by
step as the slide enters, with a dot of light travelling along the connecting lines.

```
Ceiling camera frame + planogram
        |
 1. Rectify      each planogram area is straightened to a 224 px square
        |
 2. See          DINOv3 ViT-B + ViT-L, frozen, no fine-tuning
        |        one image (about 12 areas) = one forward pass
   +----+---------------------+--------------------------+
   |                          |                          |
 3. Occupancy           4. Shelf memory            6. Product
 how much of the        the same area, compared    compared with the expected
 area is product,       patch by patch with when   product's prototype and with
 how much is crate      it was full and empty      the 93 other products
   |                          |                          |
   +------------+-------------+                          |
                |                                        |
 5. Stock level: empty / half / full          Right or wrong product
    (gradient-boosted trees)                  (and what it looks like)
                |                                        |
                +--------------------+-------------------+
                                     |
            predictions.json (official format) + tasks in the app
```

Each node is a small glass card with a mono step number, a two-word title and one line.
Hovering a node lifts it and shows its one-line explanation larger.

**6. Two ideas that make it work.** Two large liquid glass cards side by side.
- `The camera never moves.` Each area lines up with itself all day, so we compare every
  frame with the same area when full and when empty. That is why late-evening frames
  work. Visual: a small strip of the same crate through the day, fading from full to
  empty (draw it abstractly with filled and hollow cells).
- `It decides with the score in mind.` Guessing too high costs 3, too low costs 2. The
  model picks the level with the best expected score, so a doubtful shelf is called half,
  not full. Visual: three bars (empty, half, full) with a marker settling on half.

**7. Trained on real data.** Headline: `No neural network was trained.`
- Vision: DINOv3, pre-trained, frozen.
- On top: small classifiers fitted on `1,950` crops from the real day. Training takes
  about a minute on a laptop GPU.
- Labels: the dataset came with none. We made them: a first pass with AI, then corrected
  by hand by the team with a labelling tool we built; disputed areas resolved one by one.
Visual: a pipeline of three chips, `AI first pass` to `human review` to `1,950 labelled
crops`, with a count-up.

**8. AI-generated images, used to attack it.** Headline: `We used generative AI to break our own model.`
- The model we ship learned from real photos only.
- We generated edge cases to test it: the wrong fruit in a crate, nearly empty shelves,
  hands and trolleys in the way, different packaging. 16 scenarios, 6 cameras,
  119 images in our review tool.
- They showed us where it is weakest (wrong product, nearly empty shelves), and that is
  where we spent our time.
Visual: a grid of blank glass tiles labelled with scenario names that flip in.

**9. Built not to fail.** Headline: `Every area gets an answer. Always.`
A missing area costs 5 points, so the app never leaves one out. A two-column list that
ticks in line by line:
loose files with no folders (camera recognised from the picture); zip files, with macOS
debris; other resolutions, PNG, greyscale; a corrupted image (answered from the last
known state, and flagged); an image filed under the wrong camera (warned); areas partly
outside the frame; a hand or trolley in front of the shelf.

**10. The product.** Headline: `Built for the person restocking, not for the data team.`
A horizontal row of feature cards that slide in, each with a screenshot slot and one line:
- **Tasks**: restock now, wrong product, running low, in that order; mark done, undo.
- **Store wall**: every camera at a glance, areas outlined in their state colour.
- **Camera**: one camera, area by area, with how sure the model is.
- **Day replay**: scrub or play the whole day on a timeline.
- **Analytics**: store, camera, product, slot; when things went wrong and for how long.
- **Test images**: drop a folder or a zip, get `predictions.json` in the official format.
- **Search**: `Ctrl K`, in English or Portuguese.
- **ShelfOS AI**: ask about the store in plain language. It reads the model's answers;
  it does not see the photos and it does not decide any prediction.
- Light and dark, desktop and phone.

**11. Cost and speed.** Headline: `Runs on a laptop.`
Liquid glass cards with count-ups:
- `~1 s` per image on the full model, `~0.4 s` on the light one (laptop GPU, RTX 4050).
- `~1 min` to retrain from new labels.
- `0` new hardware: it uses the ceiling cameras the store already has.
- `0` cloud calls for predictions: everything runs locally with one command, `python run.py`.
Leave one clearly marked slot `[cost per store: to be filled in by the team]`. Do not
invent a monetary figure.

**12. Results.** Headline: `Measured honestly.`
Two figures with their caveat directly under them, in the same size as the caption, not
hidden: `[stock level correct: X%]` and `[right product: Y%]`, "cross-validation against
our own labels, on frames the model did not train on. The official score is the hidden
validation set." Leave the two numbers as editable placeholders at the top of the script
(`const RESULTS = { stock: null, product: null }`); when they are null show a dash.

**13. Close.** The wordmark returns, large, with `Every shelf. In sight.`
Under it: team names `[names]`, `JunctionX Lisbon 2026 · Sensei challenge`, and a glass
button `Open the live demo` linking to `http://localhost:8000`.

## Facts: do not go beyond these

Everything stated in the slides above is true and measured. Do not add statistics,
percentages, customer quotes, market sizes, savings or prices that are not written in
this prompt. In particular, the deck must never say or imply that:

- we trained or fine-tuned a neural network;
- the model was trained on synthetic or AI-generated images;
- any accuracy figure is an official score;
- the chat assistant looks at images or produces the predictions.

Where a number is missing, use the square-bracket placeholders above, and collect all of
them as constants at the top of the script so we can fill them in one place.

## What to hand back

One complete `index.html`, ready to open by double-clicking. At the top of the file, a
short comment listing the placeholders to fill in and the optional image files. Before
finishing, check the page at 1920x1080 and 1440x900 in both themes: no text overflows a
slide, nothing overlaps the navigation pill, and every slide reads in under five seconds.
