import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

function load(path, require) {
  const sandbox = { exports: {}, require };
  const source = readFileSync(new URL(path, import.meta.url), 'utf8');
  runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, sandbox);
  return sandbox.exports;
}
const lib = load('../app/lib.ts');
const { cameraConfirmed } = load('../app/colaboradores/verification.ts', () => lib);
const store = (level, timestamp = 1, extra = {}) => ({
  cameras: [{ id: '6215', areas: [{ id: '6215_1', product: 'Banana', productId: '1', quad: [] }],
    frames: [{ ts: timestamp, file: `${timestamp}.jpg`, areas: {
      '6215_1': { level, ok: true, pOk: .95, probs: [.02, .03, .95], ...extra },
    } }],
  }],
});
test('a newer clear image confirms a full shelf with the correct product', () => {
  assert.equal(cameraConfirmed(store('empty'), store('full', 2)).length, 1);
});
for (const [name, next] of [
  ['same capture', store('full')], ['still half', store('half', 2)],
  ['wrong product', store('full', 2, { ok: false })],
  ['memory answer', store('full', 2, { source: 'memory' })],
  ['obstructed shelf', store('full', 2, { obstruction: .8 })],
  ['uncertain stock', store('full', 2, { probs: [.1, .4, .5] })],
  ['uncertain product', store('full', 2, { pOk: .5 })],
]) test(`${name} cannot confirm completion`, () => {
  assert.equal(cameraConfirmed(store('empty'), next).length, 0);
});
