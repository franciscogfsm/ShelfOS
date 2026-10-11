// Renders a film page frame by frame. FILM picks the cut: unset = film.html (30 s), FILM=45 = film45.html (45 s).
//   node render.mjs                 full film -> ShelfOS-film-30s.mp4 / ShelfOS-film-45s.mp4 (needs the sound file, see audio*.py)
//   node render.mjs stills 1 5 9    single frames at those seconds -> stills<FILM>/
//   node render.mjs sheet           sixty evenly spaced frames -> stills<FILM>/
import puppeteer from 'puppeteer-core';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
const HERE = fileURLToPath(new URL('./', import.meta.url));
const TAG = process.env.FILM ?? '';
const FPS = Number(process.env.FPS ?? 60);
const SCALE = Number(process.env.SCALE ?? 1); // 2 renders 3840 x 2160
const [mode = 'film', ...rest] = process.argv.slice(2);
const chrome = process.env.CHROME ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const browser = await puppeteer.launch({ executablePath: chrome, headless: 'new', args: ['--hide-scrollbars', '--force-color-profile=srgb', '--allow-file-access-from-files'] });
const page = await browser.newPage();
page.on('console', (m) => console.log('[page]', m.text()));
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: SCALE });
await page.goto(pathToFileURL(`${HERE}film${TAG}.html`).href + '?render', { waitUntil: 'load' });
await page.evaluate(() => window.ready);
const DURATION = await page.evaluate(() => DURATION);
writeFileSync(`${HERE}cues${TAG}.json`, JSON.stringify(await page.evaluate(() => window.CUES)));
const grab = async (t, opts) => { await page.evaluate((t) => window.seek(t), t); return page.screenshot(opts); };

if (mode === 'stills' || mode === 'sheet') {
  const dir = `${HERE}stills${TAG}/`;
  mkdirSync(dir, { recursive: true });
  const times = mode === 'sheet' ? Array.from({ length: 60 }, (_, i) => (i + .5) * DURATION / 60) : rest.map(Number);
  for (const t of times) await grab(t, { path: `${dir}${t.toFixed(2).padStart(5, '0')}.jpg`, type: 'jpeg', quality: 88 });
  console.log('stills', times.length);
} else {
  const out = `${HERE}ShelfOS-film-${DURATION}s${SCALE > 1 ? "-4k" : ""}.mp4`;
  const wav = `${HERE}sound${TAG}.wav`;
  const sound = existsSync(wav) ? ['-i', wav] : [];
  const ff = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-c:v', 'mjpeg', '-threads', '2', '-framerate', String(FPS), '-i', 'pipe:0', ...sound,
    '-c:v', 'libx264', ...(SCALE > 1 ? ['-preset', 'fast', '-threads', '4', '-x264-params', 'rc-lookahead=10:ref=2:bframes=2'] : ['-preset', 'slow']), '-crf', '15', '-pix_fmt', 'yuv420p', '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-vf', 'scale=in_range=pc:out_range=tv',
    ...(sound.length ? ['-c:a', 'aac', '-b:a', '256k'] : []), '-t', String(DURATION), '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const started = Date.now();
  for (let i = 0; i < FPS * DURATION; i++) {
    const buf = await grab(i / FPS, { type: 'jpeg', quality: 97 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
    if (i % (FPS * 3) === 0) console.log(`${(i / FPS).toFixed(0)} s / ${DURATION} s  (${((Date.now() - started) / 1000).toFixed(0)} s elapsed)`);
  }
  ff.stdin.end();
  await new Promise((r) => ff.on('close', r));
  console.log('written', out);
}
await browser.close();
