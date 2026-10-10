"""Reproducible, labelled synthetic stress test. Never writes production models.

python tools/edgecases.py --models models/engine_lite.pkl models/engine.pkl
Labels are reviewed observations, NOT generation prompts or official ground truth.
Unreviewed cases remain prediction-only. All source images stay out of training.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shelfos.bank import thumbs_of
from shelfos.engine import Engine
from shelfos.features import Embedder
from shelfos.planogram import load_planogram, read_image, write_image
from shelfos.scoring import LEVELS, STOCK_PAYOFF, ID_PAYOFF


def metrics(rows):
    stock = [r for r in rows if r['expected'].get('stock_level') is not None]
    identity = [r for r in rows if r['expected'].get('planogram_compliant') is not None]
    sp = [STOCK_PAYOFF[LEVELS.index(r['prediction']['stock_level']),
                       LEVELS.index(r['expected']['stock_level'])] for r in stock]
    ip = [ID_PAYOFF[int(r['prediction']['planogram_compliant']),
                    int(r['expected']['planogram_compliant'])] for r in identity]
    return dict(stock_n=len(stock), stock_correct=int(sum(p == 1 for p in sp)),
                over=int(sum(p == -3 for p in sp)), under=int(sum(p == -2 for p in sp)),
                identity_n=len(identity), identity_correct=int(sum(p == 1 for p in ip)),
                points=float(sum(sp) + sum(ip)), maximum=len(stock) + len(identity))


def failed(row):
    return any(row['prediction'].get(k) != v for k, v in row['expected'].items()
               if k in ('stock_level', 'planogram_compliant') and v is not None)


def validate(manifest, planogram):
    ids = set()
    for case in manifest['cases']:
        if case['id'] in ids:
            raise ValueError(f"Duplicate case: {case['id']}")
        ids.add(case['id'])
        if case['split'] not in ('train', 'test'):
            raise ValueError('split must be train or test')
        camera = str(case['camera'])
        if camera not in planogram or not (ROOT / case['image']).is_file():
            raise ValueError(f"Missing image/camera for {case['id']}")
        areas = {a.area_id for a in planogram[camera]}
        for aid, label in case.get('labels', {}).items():
            if aid not in areas or label.get('stock_level') not in (None, *LEVELS):
                raise ValueError(f"Invalid label: {case['id']} {aid}")
            if label.get('planogram_compliant') not in (None, True, False):
                raise ValueError(f"Invalid compliance: {aid}")
            if label.get('stock_level') == 'empty' and label.get('planogram_compliant') is False:
                raise ValueError('Empty is compliant under organiser rules')
        if case.get('labels') and not case.get('reviewed'):
            raise ValueError(f"Unreviewed labels: {case['id']}")
    # Exact copies cannot cross the training/test boundary, regardless of file names.
    split_hashes = defaultdict(set)
    for c in manifest['cases']:
        split_hashes[hashlib.sha256((ROOT / c['image']).read_bytes()).hexdigest()].add(c['split'])
    if any(len(s) > 1 for s in split_hashes.values()):
        raise ValueError('An identical image occurs in both train and test')
    families = defaultdict(set)
    for c in manifest['cases']:
        if c.get('source_group'):
            families[c['source_group']].add(c['split'])
    if any(len(s) > 1 for s in families.values()):
        raise ValueError('A source family occurs in both train and test')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', default='ai_generated_edgecases/manifest.json')
    ap.add_argument('--models', nargs='+', default=['models/engine_lite.pkl', 'models/engine.pkl'])
    ap.add_argument('--out', default='outputs/edgecases')
    ap.add_argument('--device', default=None)
    args = ap.parse_args()
    manifest = json.loads((ROOT / args.manifest).read_text(encoding='utf-8'))
    pg = load_planogram(ROOT / 'data/planogram.json')
    validate(manifest, pg)
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / 'manifest-snapshot.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    all_rows, summaries = [], []
    for model_path in args.models:
        started = time.perf_counter()
        engine = Engine.load(ROOT / model_path)
        emb = Embedder(engine.model_name, args.device, engine.crop_size, engine.tta)
        emb.warmup()
        load_seconds = time.perf_counter() - started
        model_rows, latencies, predictions = [], [], {}
        for case in manifest['cases']:
            frame = read_image(ROOT / case['image'])
            if frame is None:
                raise ValueError(f"Undecodable image: {case['image']}")
            raw_shape = frame.shape[:2][::-1]
            warning = None
            expected_w, expected_h = engine.frame_size
            if abs(raw_shape[0] / raw_shape[1] - expected_w / expected_h) > .03:
                warning = 'Aspect ratio differs from real camera; geometry may be invalid. Not scored.'
            frame = cv2.resize(frame, engine.frame_size)
            areas = pg[str(case['camera'])]
            t0 = time.perf_counter()
            crops = [emb.crop(frame, area) for area in areas]
            glob, patches = emb.embed(crops, compact=False)
            pred = engine.predict(glob, patches, thumbs_of(crops), areas, fname=case.get('capture_name', case['id']+'.png'))
            ms = (time.perf_counter() - t0) * 1000
            latencies.append(ms)
            predictions[case['id']] = {a.area_id: p for a, p in zip(areas, pred)}
            for area, crop, p in zip(areas, crops, pred):
                expected = case.get('labels', {}).get(area.area_id, {}) if not warning else {}
                crop_path = f"crops/{case['id']}/{area.area_id}.jpg"
                if not (out / crop_path).exists():
                    write_image(out / crop_path, crop)
                row = dict(model=Path(model_path).stem, case=case['id'], camera=case['camera'],
                           scenario=expected.get('scenario', case['scenario']), split=case['split'],
                           area=area.area_id, product=area.product_name, crop=crop_path,
                           expected=expected, prediction=p, warning=warning)
                model_rows.append(row)
            print(f"{Path(model_path).stem}: {case['id']} {len(areas)} areas {ms:.0f}ms", flush=True)
        test = [r for r in model_rows if r['split'] == 'test']
        by_scenario = {s: metrics([r for r in test if r['scenario'] == s]) for s in sorted({r['scenario'] for r in test})}
        summary = dict(model=model_path, sha256=hashlib.sha256((ROOT / model_path).read_bytes()).hexdigest(),
                       code_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                                    ('shelfos/engine.py', 'shelfos/memory.py', 'shelfos/compliance.py', 'shelfos/features.py')},
                       load_seconds=load_seconds, images=len(latencies), areas=len(model_rows),
                       median_ms=float(np.median(latencies)), p95_ms=float(np.percentile(latencies, 95)),
                       test=metrics(test), by_scenario=by_scenario)
        summaries.append(summary)
        all_rows.extend(model_rows)
        (out / f'{Path(model_path).stem}-predictions.json').write_text(json.dumps(predictions, indent=2), encoding='utf-8')
        del engine, emb
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    (out / 'results.json').write_text(json.dumps(dict(summaries=summaries, rows=all_rows), indent=2), encoding='utf-8')
    lines = ['# Synthetic edge-case comparison', '', 'Against visually reviewed local labels; not official ground truth.',
             'Train cases are excluded from every score. Aspect-ratio mismatches are prediction-only.', '',
             '| Model | Stock correct | Over / under | Compliance correct | Points / max | Median / p95 frame ms |',
             '|---|---:|---:|---:|---:|---:|']
    for s in summaries:
        m = s['test']
        lines.append(f"| {Path(s['model']).stem} | {m['stock_correct']}/{m['stock_n']} | {m['over']} / {m['under']} | {m['identity_correct']}/{m['identity_n']} | {m['points']:g}/{m['maximum']} | {s['median_ms']:.0f} / {s['p95_ms']:.0f} |")
    for s in summaries:
        lines += ['', f"## {Path(s['model']).stem}: scenarios", '', '| Scenario | Points / max | Stock over |', '|---|---:|---:|']
        for scenario, m in s['by_scenario'].items():
            if m['maximum']:
                lines.append(f"| {scenario} | {m['points']:g}/{m['maximum']} | {m['over']} |")
    lines += ['', '## Failures', '']
    for r in all_rows:
        if r['split'] == 'test' and failed(r):
            lines.append(f"- {r['model']} / {r['case']} / {r['area']}: expected {r['expected']}; predicted {r['prediction']['stock_level']}, compliant={r['prediction']['planogram_compliant']}; novelty={r['prediction']['obstruction']}.")
    (out / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    cards = []
    for r in sorted(all_rows, key=lambda r: (not failed(r), r['case'], r['area'], r['model'])):
        e, p = r['expected'], r['prediction']
        status = 'FAIL' if failed(r) else 'OK' if e else 'UNLABELLED'
        cards.append(f"<article data-status='{status}'><img loading='lazy' src='{html.escape(r['crop'])}'><div><b>{html.escape(r['model'])} · {status}</b><p>{html.escape(r['case'])} / {r['area']}<br>{html.escape(r['product'])}</p><p>Expected: {html.escape(json.dumps(e))}<br>Predicted: {p['stock_level']} · compliant {p['planogram_compliant']}<br>Stock probabilities: {p['stock_probs']} · occupancy {p['occupancy']} · novelty {p['obstruction']}</p><small>{html.escape(r['warning'] or r['split'])}</small></div></article>")
    page = "<!doctype html><meta charset='utf-8'><title>ShelfOS edge-case review</title><style>body{background:#101114;color:#eee;font:15px system-ui;margin:30px}header{position:sticky;top:0;background:#101114;padding:15px}article{display:flex;gap:20px;border:1px solid #333;border-radius:12px;margin:12px 0;padding:15px}img{width:180px;height:180px;object-fit:contain}article[data-status=FAIL]{border-color:#ff6578}p{line-height:1.6}small{color:#aaa}button{padding:10px;margin:5px;cursor:pointer}</style><header><h1>ShelfOS · edge-case review</h1><p>Visually reviewed synthetic labels. Unlabelled cases are not accuracy evidence.</p><button onclick=\"document.querySelectorAll('article').forEach(a=>a.hidden=a.dataset.status!=='FAIL')\">Failures only</button><button onclick=\"document.querySelectorAll('article').forEach(a=>a.hidden=false)\">All areas</button></header>" + ''.join(cards)
    (out / 'review.html').write_text(page, encoding='utf-8')
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == '__main__':
    main()
