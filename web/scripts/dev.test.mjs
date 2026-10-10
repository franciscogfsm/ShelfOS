import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ensureEnv, backendReady, chooseBackend } from './dev.mjs';

test('creates env once and preserves the user key on subsequent starts', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'shelfos-dev-'));
  try {
    await writeFile(join(dir, '.env.example'), 'OPENROUTER_API_KEY=\n');
    await ensureEnv(dir);
    assert.equal(await readFile(join(dir, '.env'), 'utf8'), 'OPENROUTER_API_KEY=\n');
    await writeFile(join(dir, '.env'), 'OPENROUTER_API_KEY=user-test-value\n');
    await ensureEnv(dir);
    assert.equal(await readFile(join(dir, '.env'), 'utf8'), 'OPENROUTER_API_KEY=user-test-value\n');
  } finally { await rm(dir, { recursive: true }); }
});

test('reuses a ready assistant backend, skips unrelated/outdated listeners', async () => {
  let assistant = false;
  const server = createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    if (req.url === '/api/health') res.end(JSON.stringify({ ready: true }));
    else if (assistant && req.url === '/api/assistant') res.end(JSON.stringify({ configured: false, model: 'test' }));
    else { res.statusCode = 404; res.end('{}'); }
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  try {
    assert.equal(await backendReady(`http://localhost:${port}`), false);
    assert.notEqual((await chooseBackend(port)).port, port);
    assistant = true;
    assert.deepEqual(await chooseBackend(port), { port, url: `http://localhost:${port}`, reuse: true });
  } finally { server.closeAllConnections(); await new Promise(r => server.close(r)); }
});
