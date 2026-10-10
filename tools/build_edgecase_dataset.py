"""Assemble generated assets without altering pixels; create manifest and review gallery."""
from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'ai_generated_edgecases'
OUT = BASE / 'dataset_large'


def main():
    plan = json.loads((BASE / 'bulk_generation_plan.json').read_text(encoding='utf-8'))
    original = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    cases, pending, cards, seen = [], [], [], {}
    assets = [(c, ROOT / c['image'], 'previous') for c in original['cases']]
    for job in plan['cases']:
        result = BASE / 'bulk_results' / (job['id'] + '.json')
        if not result.exists():
            pending.append(job['id'])
            continue
        metadata = json.loads(result.read_text(encoding='utf-8'))
        path = metadata.get('generated_path')
        if not path or not Path(path).is_file() or metadata.get('isError'):
            pending.append(job['id'])
            continue
        assets.append((job, Path(path), 'new_generation'))
    for case, source, origin in assets:
        with Image.open(source) as im:
            width, height = im.size
            im.verify()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        relative = Path('images') / case['split'] / case['scenario'] / (case['id'] + source.suffix.lower())
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            # Both paths retain the file; hard links avoid duplicating large PNGs.
            if target.exists():
                target.unlink()
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
        item = dict(case, image=target.relative_to(ROOT).as_posix(), origin=origin,
                    sha256=digest, dimensions=[width, height], duplicate_of=seen.get(digest),
                    label_status='reviewed_local' if case.get('reviewed') else 'needs_label_review')
        seen.setdefault(digest, case['id'])
        cases.append(item)
        caption = html.escape(f"{case['id']} · {case['camera']} · {case['split']}")
        label = html.escape(item['label_status'])
        prompt = html.escape(case.get('prompt', 'Existing dataset image; see labels in manifest.'))
        cards.append(f"<article data-scenario='{html.escape(case['scenario'])}' data-status='{label}'><a href='{relative.as_posix()}' target='_blank'><img loading='lazy' src='{relative.as_posix()}' alt='{caption}'></a><h3>{caption}</h3><p>{label} · {width}×{height}</p><details><summary>Scenario / prompt</summary><p>{prompt}</p></details></article>")
    references = []
    for source_name in sorted({j['source'] for j in plan['cases']}):
        source = ROOT / source_name
        camera = source.parent.name
        relative = Path('reference_sources') / f'{camera}_{source.name}'
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            try:
                os.link(source, target)
            except OSError:
                shutil.copy2(source, target)
        references.append(dict(camera=camera, source=source_name, image=relative.as_posix()))
        cards.append(f"<article data-scenario='reference_source' data-status='source_reference'><a href='{relative.as_posix()}' target='_blank'><img loading='lazy' src='{relative.as_posix()}'></a><h3>Real source · camera {camera}</h3><p>Reference only, excluded from test scores. Compare geometry and unchanged regions with generated variants.</p></article>")
    manifest = dict(version=1, purpose='synthetic challenge dataset; no automatic training',
                    reference_sources=references,
                    notes=original.get('notes', []) + [
                        'New generated images have no scored labels until visual area-level review.',
                        'Many variants share six real source frames: they are not independent observations.',
                        'Production may have trained on the real source frames. This is a stress test, not an unbiased generalisation benchmark.',
                        'Original TRAIN references stay in images/train and must not contribute to TEST scores.',
                        'Prompts describe intentions, not ground truth; generation can change geometry or unrelated objects.'
                    ], cases=cases)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    stats = dict(total_images=len(cases), unique_images=len(seen),
                 real_source_frames=len(references), image_files_total=len(cases)+len(references),
                 test_images=sum(c['split'] == 'test' for c in cases),
                 train_references=sum(c['split'] == 'train' for c in cases),
                 new_generated=sum(c['origin'] == 'new_generation' for c in cases),
                 scenarios=dict(Counter(c['scenario'] for c in cases)),
                 cameras=dict(Counter(c['camera'] for c in cases)),
                 pending_generation=pending)
    (OUT / 'inventory.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')
    options = ''.join(f"<option>{html.escape(s)}</option>" for s in sorted([*stats['scenarios'], 'reference_source']))
    page = """<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>ShelfOS · Edge-case dataset</title><style>body{margin:24px;background:#101114;color:#eee;font:15px system-ui}header{position:sticky;top:0;background:#101114f5;padding:16px 0;z-index:1}h1{margin:0 0 10px}select{padding:10px;background:#202228;color:#fff;border:1px solid #444;border-radius:8px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}article{border:1px solid #333;padding:12px;border-radius:12px;min-width:0}article[hidden]{display:none}img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#08090b}h3{font-size:13px;overflow-wrap:anywhere}p{color:#bbb;line-height:1.5}details p{font-size:12px}a{color:#c5b7ff}</style><header><h1>ShelfOS · Edge-case dataset</h1>"""
    page += f"<p>{len(cases)} synthetic cases + {len(references)} real reference frames · {stats['new_generated']} new generations. New cases need area-level label review; prompts are not ground truth.</p><select id='scenario' onchange='filter()'><option value=''>All scenarios</option>{options}</select> <select id='status' onchange='filter()'><option value=''>All review statuses</option><option>needs_label_review</option><option>reviewed_local</option><option>source_reference</option></select></header><main>" + ''.join(cards)
    page += "</main><script>function filter(){const s=document.querySelector('#scenario').value,r=document.querySelector('#status').value;document.querySelectorAll('article').forEach(a=>a.hidden=!!((s&&a.dataset.scenario!==s)||(r&&a.dataset.status!==r)))}</script></html>"
    (OUT / 'index.html').write_text(page, encoding='utf-8')
    (OUT / 'README.md').write_text(f'''# Large edge-case dataset

{len(cases)} full synthetic camera images, including {stats['new_generated']} new AI-generated images, plus {len(references)} real source photographs in `reference_sources/` for visual comparison. References are not scored. Images are grouped by split and scenario under `images/`. Open `index.html` to browse and filter; click an image for the original full resolution. No pixels are changed by the assembly script. Where supported, image paths are hard links to their saved source files to avoid doubling disk use; treat this collection as read-only and save any edits into separate files.

`manifest.json` records image path, camera, original source family, generation prompt, hash, dimensions, review status and any previously reviewed labels. `inventory.json` records actual counts and unfinished generation IDs. New generated images are **unlabelled**: inspect the output and planogram before adding area labels. Do not infer labels from a prompt, and do not score unreadable or displaced geometry.

Many images share six real frames. This gives scenario coverage, not {len(cases)} independent scenes. Production may know these real frames; use separate real temporal holdouts to judge deployment gains. Four previous TRAIN references are kept in `images/train`, never mixed into TEST scores. Keep all variants of one source family in one split when extending training.

Rebuild the folder and gallery from saved outputs:

```powershell
python tools/build_edgecase_dataset.py
```

Run inference using the existing evaluator (new images are prediction-only until reviewed):

```powershell
python tools/edgecases.py --manifest ai_generated_edgecases/dataset_large/manifest.json --out outputs/edgecases_large
```

The existing reviewed benchmark and Fable brief remain in the parent folder. Existing benchmarks do not automatically include new cases. Do not train on this test folder; create a separate reviewed training set and compare against fixed tests first.
''', encoding='utf-8')
    print(json.dumps({**stats, 'pending_generation': len(pending)}, indent=2))


if __name__ == '__main__':
    main()
