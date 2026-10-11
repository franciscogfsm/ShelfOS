import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { cp, mkdir, readFile, writeFile, access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const web = fileURLToPath(new URL('../', import.meta.url));
const require = createRequire(resolve(web, 'package.json'));
const result = spawnSync(process.execPath, [require.resolve('next/dist/bin/next'), 'build'], {
  cwd: web, stdio: 'inherit',
  env: { ...process.env, NEXT_PUBLIC_DEMO: 'true', NEXT_PUBLIC_API: '', SHELFOS_DEV_DIST: '.next-vercel-demo' },
});
if (result.status !== 0) process.exit(result.status ?? 1);
// Next exports to the configured distDir when it differs from .next.
const exported = resolve(web, '.next-vercel-demo');
await access(resolve(exported, 'index.html'));
const destination = resolve(web, '..', 'vercel-demo');
await mkdir(destination, { recursive: true });
await cp(exported, resolve(destination, 'public'), { recursive: true });
await writeFile(resolve(destination, 'vercel.json'), JSON.stringify({
  framework: null, buildCommand: '', installCommand: '', outputDirectory: 'public', cleanUrls: true,
}, null, 2));
await writeFile(resolve(destination, '.vercelignore'), 'README.md\n');
await writeFile(resolve(destination, 'README.md'), `# ShelfOS — demo para Vercel

Esta pasta já está compilada. Não precisa de Python, modelos, GPU, chaves nem npm install.

Publicar a partir desta pasta:

    npx vercel --prod

No painel Vercel, também podes importar um repositório que contenha apenas esta pasta.
Framework: Other. Output Directory: public. Build Command: vazio.

Depois de publicar:
- Web normal / QR: https://TEU-DOMINIO.vercel.app/
- Colaboradores / QR: https://TEU-DOMINIO.vercel.app/colaboradores

Inclui os 181 frames do dia, produtos, caixas clicáveis, detalhes, replay, analytics e tarefas.
A página dos colaboradores simula a confirmação da reposição. Não executa inferência nova,
contagem, avaliação de maturação ou chat AI sem o backend.

Para voltar a gerar esta pasta: npm --prefix web run package:vercel
`);
// Check every bundled camera image, so broken snapshot links cannot ship unnoticed.
const store = JSON.parse(await readFile(resolve(destination, 'public/data/store.json'), 'utf8'));
let images = 0;
for (const camera of store.cameras) for (const frame of camera.frames) {
  await access(resolve(destination, 'public/frames', camera.id, frame.file));
  images++;
}
await access(resolve(destination, 'public/colaboradores.html'));
console.log(`Vercel demo ready: ${destination} (${images} camera images verified).`);
