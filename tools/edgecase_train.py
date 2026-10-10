"""Low-weight synthetic stock-head experiment with a genuine real late-frame holdout.

python tools/edgecase_train.py
Fits a baseline on earlier REAL frames. Adds reviewed TRAIN synthetic crops only to
its stock head, retaining occupancy, memory and compliance. No production overwrite.
Real holdout and synthetic test images never enter fitting. Candidate promotion is
manual and requires both real and synthetic held-out scores to improve.
"""
import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shelfos.bank import thumbs_of
from shelfos.engine import Engine, bank_labels, hour_features
from shelfos.features import Embedder
from shelfos.occupancy import patch_tokens, occupancy_features
from shelfos.planogram import load_planogram, read_image
from shelfos.scoring import STOCK_PAYOFF, LEVELS, ID_PAYOFF
from tools.edgecases import validate


def evaluate_real(engine, bank, indices, y, comply):
    areas = [SimpleNamespace(area_id=str(bank['area'][i]), product_id=str(bank['product'][i])) for i in indices]
    pred = engine.predict(bank['glob'][indices], bank['patches'][indices], bank['thumbs'][indices], areas, fname=bank['fname'][indices])
    stock = [STOCK_PAYOFF[LEVELS.index(p['stock_level']), y[i]] for i, p in zip(indices, pred) if y[i] >= 0]
    identity = [ID_PAYOFF[int(p['planogram_compliant']), int(comply[i])] for i, p in zip(indices, pred) if comply[i] >= 0]
    return dict(stock_n=len(stock), stock_correct=int(sum(s == 1 for s in stock)),
                over=int(sum(s == -3 for s in stock)), under=int(sum(s == -2 for s in stock)),
                identity_correct=int(sum(s == 1 for s in identity)), identity_n=len(identity),
                points=float(sum(stock) + sum(identity)), maximum=len(stock) + len(identity))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bank', default='cache/bank_tta.npz')
    ap.add_argument('--manifest', default='ai_generated_edgecases/manifest.json')
    ap.add_argument('--weight', type=float, default=.25)
    ap.add_argument('--out', default='models/edgecases')
    args = ap.parse_args()
    if not 0 < args.weight <= 1:
        ap.error('Synthetic weight must be >0 and <=1')
    out = ROOT / args.out
    if out.resolve() == (ROOT / 'models').resolve():
        ap.error('Use a separate experimental model directory')
    out.mkdir(parents=True, exist_ok=True)
    pg = load_planogram(ROOT / 'data/planogram.json')
    manifest = json.loads((ROOT / args.manifest).read_text())
    validate(manifest, pg)
    training = [c for c in manifest['cases'] if c['split'] == 'train' and c.get('reviewed')]
    if not training:
        raise SystemExit('No reviewed TRAIN cases. Do not train on TEST images.')
    train_groups = {c['source_group'] for c in training}
    if train_groups & {c['source_group'] for c in manifest['cases'] if c['split'] == 'test'}:
        raise SystemExit('Train and test share a synthetic source family')
    bank = dict(np.load(ROOT / args.bank))
    y, sure, c, cs = bank_labels(bank, ROOT / 'labels/silver_labels.txt')
    last = np.array([bank['t'][bank['camera'] == cam].max() for cam in bank['camera']])
    holdout = last - bank['t'] <= 1
    tr = ~holdout
    print(f'Fit baseline: {tr.sum()} real crops; holdout {holdout.sum()} crops', flush=True)
    engine = Engine.fit(bank, ROOT / 'labels/silver_labels.txt', ROOT / 'labels/background_rects.txt', rows=tr)
    engine.model_name, engine.crop_size, engine.tta = str(bank['model']), int(bank['size']), bool(bank['tta'])
    truth_c = np.where(y == 0, 1, c)
    before = evaluate_real(engine, bank, np.flatnonzero(holdout), y, truth_c)
    engine.save(out / 'edge_baseline.pkl')
    # Exactly the baseline stock-head design, including leave-self-out memory.
    use = tr & (y >= 0)
    idx = np.flatnonzero(use)
    maps = engine.occ.maps(patch_tokens(bank['patches'][idx], bank['thumbs'][idx]))
    f = occupancy_features(maps)
    R = engine.memory.features(bank['glob'][idx], bank['patches'][idx], f[:, 0], bank['area'][idx], self_row=np.arange(len(idx)))
    X = engine._design(bank['glob'][idx], f, R, hour_features(bank['fname'][idx], len(idx)))
    del maps, R
    emb = Embedder(engine.model_name, size=engine.crop_size, tta=engine.tta)
    crops, areas, names, syn_y = [], [], [], []
    for case in training:
        # Reference source must be an earlier frame, not one of the real holdout frames.
        source = case.get('source_image', '')
        source_name = Path(source).name
        match = (bank['camera'] == case['camera']) & (bank['fname'] == source_name)
        if not match.any() or holdout[match].any():
            raise ValueError(f"Training edit must originate in the real training split: {case['id']}")
        frame = read_image(ROOT / case['image'])
        if abs(frame.shape[1] / frame.shape[0] - 1280/720) > .03:
            raise ValueError('Training edit has changed aspect ratio')
        frame = cv2.resize(frame, engine.frame_size)
        for a in pg[case['camera']]:
            lab = case['labels'].get(a.area_id, {})
            if lab.get('stock_level') is None:
                continue
            crops.append(emb.crop(frame, a)); areas.append(a); names.append(source_name)
            syn_y.append(LEVELS.index(lab['stock_level']))
    glob, patches = emb.embed(crops, compact=False)
    f = occupancy_features(engine.occ.maps(patch_tokens(patches, thumbs_of(crops))))
    area_ids = np.array([a.area_id for a in areas])
    R = engine.memory.features(glob, patches, f[:, 0], area_ids,
                               self_row=engine.memory.rows_of(area_ids, names))
    SX = engine._design(glob, f, R, hour_features(names, len(names)))
    engine.stock_clf = LogisticRegression(C=Engine.STOCK_C, max_iter=3000).fit(
        np.vstack([X, SX]), np.concatenate([y[idx], syn_y]),
        sample_weight=np.concatenate([np.where(sure[idx], 1., .5), np.full(len(syn_y), args.weight)]))
    after = evaluate_real(engine, bank, np.flatnonzero(holdout), y, truth_c)
    engine.save(out / 'edge_candidate.pkl')
    report = dict(real_split='last two frames per camera; earlier real frames only in training',
                  synthetic_train_crops=len(syn_y), synthetic_weight=args.weight,
                  baseline=before, candidate=after, real_delta=after['points'] - before['points'],
                  promoted=False, next_check='Compare baseline and candidate on manifest TEST cases with tools/edgecases.py. Do not select on training accuracy.')
    Path('outputs/edgecase_training').mkdir(parents=True, exist_ok=True)
    Path('outputs/edgecase_training/real_holdout.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
