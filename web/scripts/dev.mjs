import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createServer } from 'node:net';

const web = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(web, '..');
const children = new Set();
let stopping = false;

export async function ensureEnv(directory = root) {
  try {
    await writeFile(resolve(directory, '.env'), await readFile(resolve(directory, '.env.example')), { flag: 'wx' });
    console.log('[ShelfOS] Created .env — add OPENROUTER_API_KEY there to enable chat.');
  } catch (error) { if (error.code !== 'EEXIST') throw error; }
}

export async function backendReady(url) {
  try {
    const [health, assistant] = await Promise.all([
      fetch(`${url}/api/health`, { signal: AbortSignal.timeout(1500) }),
      fetch(`${url}/api/assistant`, { signal: AbortSignal.timeout(1500) }),
    ]);
    if (!health.ok || !assistant.ok) return false;
    const h = await health.json(), a = await assistant.json();
    return h.ready === true && typeof a.configured === 'boolean' && typeof a.model === 'string';
  } catch { return false; }
}

async function available(port) {
  return new Promise(resolvePort => {
    const probe = createServer();
    probe.once('error', () => resolvePort(false));
    probe.listen(port, '127.0.0.1', () => probe.close(() => resolvePort(true)));
  });
}

export async function chooseBackend(first = 8000) {
  for (let port = first; port < first + 20 && port <= 65535; port++) {
    const url = `http://localhost:${port}`;
    if (await backendReady(url)) return { port, url, reuse: true };
    if (await available(port)) return { port, url, reuse: false };
  }
  throw Error('No backend port is available. Set SHELFOS_API_PORT to a free port.');
}

function launch(command, args, options) {
  const child = spawn(command, args, { stdio: 'inherit', windowsHide: true, ...options });
  children.add(child);
  child.once('error', error => { console.error(`[ShelfOS] ${error.message}`); shutdown(1); });
  child.once('exit', (code, signal) => {
    children.delete(child);
    if (!stopping) { console.error(`[ShelfOS] ${command} stopped (${signal ?? code}).`); shutdown(code ?? 1); }
  });
  return child;
}

function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (process.platform === 'win32') {
      // Only the processes this launcher owns, including Next's workers.
      const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true });
      killer.on('error', () => child.kill());
    } else child.kill('SIGTERM');
  }
  setTimeout(() => process.exit(code), 800);
}

export async function main() {
  await ensureEnv();
  const port = Number(process.env.SHELFOS_API_PORT ?? 8000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error('SHELFOS_API_PORT must be a valid port.');
  const backend = await chooseBackend(port);
  if (backend.reuse) console.log(`[ShelfOS] Using existing backend: ${backend.url}`);
  else {
    console.log(`[ShelfOS] Starting backend: ${backend.url} (first run may prepare the model)`);
    const python = launch(process.env.PYTHON ?? 'python', ['-u', resolve(root, 'run.py'), '--no-browser', '--port', String(backend.port)], { cwd: root });
    const started = Date.now(); let lastNotice = 0;
    while (!await backendReady(backend.url)) {
      if (stopping || python.exitCode !== null) return;
      if (Date.now() - started > 300000) throw Error('Backend startup timed out. Check the Python output above.');
      if (Date.now() - lastNotice > 15000) { console.log('[ShelfOS] Waiting for the inference backend…'); lastNotice = Date.now(); }
      await new Promise(r => setTimeout(r, 500));
    }
  }
  if (stopping) return;
  console.log('[ShelfOS] Backend ready. Starting web UI; Ctrl+C stops both.');
  const require = createRequire(resolve(web, 'package.json'));
  launch(process.execPath, [require.resolve('next/dist/bin/next'), 'dev', ...process.argv.slice(2)], {
    cwd: web, env: { ...process.env, NEXT_PUBLIC_API: backend.url },
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.on('SIGINT', () => shutdown());
  process.on('SIGTERM', () => shutdown());
  main().catch(error => { console.error(`[ShelfOS] ${error.message}`); shutdown(1); });
}
