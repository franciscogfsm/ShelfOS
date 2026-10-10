"""Human annotation UI. Run from any directory: python tools/label_review.py.

Only --apply changes the source labels. Review sessions and exports are resumable.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
from shelfos.labels import load_labels
from shelfos.planogram import list_images, load_planogram, read_image


@contextmanager
def session_lock(path):
    """One process per session; OS releases the lock even if Python crashes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix('.lock')
    with lock_path.open('a+b') as stream:
        if lock_path.stat().st_size == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('This session is already open. Stop its server with Ctrl+C, or use another --state.') from error
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content if isinstance(content, bytes) else content.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def parse_labels(text):
    result = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        aid, stock, comply = (part.strip() for part in line.split('|'))
        if aid in result or len(stock) != len(comply):
            raise ValueError(f'Invalid labels for {aid}')
        result[aid] = (stock, comply)
    return result


class Review:
    def __init__(self, labels, planogram, images, state, scope='all', task='stock'):
        self.labels, self.state = Path(labels).resolve(), Path(state).resolve()
        self.scope, self.task = scope, task
        self.lock = threading.RLock()
        try:
            label_identity = self.labels.relative_to(ROOT).as_posix()
        except ValueError:
            label_identity = str(self.labels)
        self.areas = {a.area_id: a for group in load_planogram(planogram).values() for a in group}
        self.files = list_images(images)
        if self.state.exists():
            self.session = json.loads(self.state.read_text(encoding='utf-8'))
            if self.session.get('version') != 1 or self.session['labels_path'] != label_identity:
                raise ValueError('Session belongs to another labels file; choose a new --state path.')
        else:
            self.session = dict(version=1, labels_path=label_identity,
                                baseline=self.labels.read_text(encoding='utf-8-sig'), answers={})
        self.base = parse_labels(self.session['baseline'])
        current = parse_labels(self.labels.read_text(encoding='utf-8-sig'))
        if {a: len(s) for a, (s, _) in current.items()} != {a: len(s) for a, (s, _) in self.base.items()}:
            raise ValueError('Area/frame structure changed; choose a new --state path.')
        self.items = []
        for aid, (stock, comply) in self.base.items():
            a = self.areas[aid]
            files = self.files[a.camera]
            if len(files) != len(stock):
                raise ValueError(f'{aid}: {len(files)} images but {len(stock)} labels')
            for t, (s, c) in enumerate(zip(stock, comply)):
                self.items.append(dict(id=f'{aid}:{t}', area=aid, camera=a.camera, t=t,
                                       filename=files[t].name, product=a.product_name,
                                       old=s, old_comply=c,
                                       uncertain=not s.isupper() or s not in 'EHF'))
        self.by_id = {x['id']: x for x in self.items}
        frame_names = {x['id']: x['filename'] for x in self.items}
        if 'frames' in self.session and self.session['frames'] != frame_names:
            raise ValueError('Image names/order changed; choose a new --state path.')
        self.session['frames'] = frame_names
        for key, answer in self.session['answers'].items():
            if key not in self.by_id or answer.get('stock') not in ['E', 'H', 'F', '?']:
                raise ValueError(f'Invalid saved answer: {key}')
            if answer.get('comply') not in [None, 'T', 'F', 'N']:
                raise ValueError(f'Invalid saved compliance: {key}')

    @property
    def output(self):
        return self.state.parent / 'reviewed_labels.txt'

    def save(self):
        atomic_write(self.state, json.dumps(self.session, ensure_ascii=False, indent=2))

    def merge(self, source):
        current = parse_labels(source)
        conflicts, lines = [], []
        for key in self.session['answers']:
            aid, t = key.split(':')
            if aid not in current or int(t) >= len(current[aid][0]):
                conflicts.append(dict(id=key, field='structure'))
        for line in source.splitlines(keepends=True):
            if not line.strip() or line.lstrip().startswith('#'):
                lines.append(line)
                continue
            parts = line.split('|')
            aid = parts[0].strip()
            for column, field in [(1, 'stock'), (2, 'comply')]:
                segment = parts[column]
                chars = list(segment.strip())
                for t, old in enumerate(chars):
                    key = f'{aid}:{t}'
                    chosen = self.session['answers'].get(key, {}).get(field)
                    if chosen is None:
                        continue
                    baseline = self.base[aid][column - 1][t] if aid in self.base and t < len(self.base[aid][0]) else None
                    if old not in [baseline, chosen]:
                        conflicts.append(dict(id=key, field=field, source=old, human=chosen))
                    else:
                        chars[t] = chosen
                start, end = len(segment) - len(segment.lstrip()), len(segment.rstrip())
                parts[column] = segment[:start] + ''.join(chars) + segment[end:]
            lines.append('|'.join(parts))
        return ''.join(lines), conflicts

    def export(self):
        merged, conflicts = self.merge(self.labels.read_text(encoding='utf-8-sig'))
        atomic_write(self.output, merged)
        atomic_write(self.state.parent / 'conflicts.json', json.dumps(conflicts, indent=2))
        return conflicts

    def answer(self, key, stock, comply=None, expected=None):
        if key not in self.by_id or stock not in ['E', 'H', 'F', '?'] or comply not in [None, 'T', 'F', 'N']:
            raise ValueError('Invalid answer')
        with self.lock:
            if self.session['answers'].get(key) != expected:
                raise ValueError('Another browser changed this answer. Reload before answering.')
            answer = dict(stock=stock, comply=comply,
                          reviewed_at=datetime.now(timezone.utc).isoformat())
            previous = self.session['answers'].get(key)
            self.session['answers'][key] = answer
            try:
                self.save()
            except Exception:
                if previous is None:
                    self.session['answers'].pop(key)
                else:
                    self.session['answers'][key] = previous
                raise
            try:
                conflicts = self.export()
                warning = None
            except OSError as error:
                conflicts, warning = [], f'Answer saved, but export failed: {error}'
            return dict(answer=answer, conflicts=conflicts, warning=warning)

    def apply(self):
        with self.lock:
            original = self.labels.read_bytes()
            merged, conflicts = self.merge(original.decode('utf-8-sig'))
            if conflicts:
                atomic_write(self.state.parent / 'conflicts.json', json.dumps(conflicts, indent=2))
                raise ValueError(f'{len(conflicts)} conflicts; source unchanged. See conflicts.json.')
            backup = self.state.parent / ('backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.txt')
            atomic_write(backup, original)
            if self.labels.read_bytes() != original:
                raise ValueError('Source changed during apply; retry after the other writer finishes.')
            atomic_write(self.labels, merged)
            loaded = load_labels(self.labels)
            for key, answer in self.session['answers'].items():
                aid, t = key.split(':')
                assert loaded[aid][int(t)].stock == {'E': 0, 'H': 1, 'F': 2, '?': None}[answer['stock']]
            self.session['baseline'] = merged
            self.base = parse_labels(merged)
            self.save()
            return backup

    def image(self, key, kind):
        item = self.by_id[key]
        a = self.areas[item['area']]
        image = read_image(self.files[item['camera']][item['t']])
        if image is None:
            raise ValueError('Unreadable image')
        if kind == 'crop':
            image, valid = a.warp(image, a.rect_size(600))
            image[~valid] = (100, 0, 100)
        else:
            cv2.polylines(image, [np.round(a.quad).astype(np.int32)], True, (0, 255, 255), 5)
            if kind == 'near':
                lo, hi = a.quad.min(axis=0), a.quad.max(axis=0)
                pad = np.maximum((hi - lo) * .7, 65)
                lo = np.maximum(0, np.floor(lo - pad)).astype(int)
                hi = np.minimum([image.shape[1], image.shape[0]], np.ceil(hi + pad)).astype(int)
                image = image[lo[1]:hi[1], lo[0]:hi[0]]
            elif image.shape[1] > 1400:
                image = cv2.resize(image, (1400, round(image.shape[0] * 1400 / image.shape[1])))
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if not ok:
            raise ValueError('Could not encode image')
        return encoded.tobytes()


def handler_for(review):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, data, mime='application/json', status=200):
            if isinstance(data, (dict, list)):
                data = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            try:
                url = urlparse(self.path)
                if url.path == '/':
                    self.send(Path(__file__).with_suffix('.html').read_bytes(), 'text/html; charset=utf-8')
                elif url.path == '/data':
                    with review.lock:
                        self.send(dict(items=review.items, answers=review.session['answers'],
                                       scope=review.scope, task=review.task,
                                       output=str(review.output), conflicts=review.export()))
                elif url.path == '/image':
                    query = parse_qs(url.query)
                    self.send(review.image(query['id'][0], query.get('kind', ['crop'])[0]), 'image/jpeg')
                else:
                    self.send({}, status=404)
            except (ValueError, KeyError, OSError) as error:
                self.send(dict(error=str(error)), status=400)

        def do_POST(self):
            if self.path != '/answer':
                self.send({}, status=404)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096:
                    raise ValueError('Invalid request size')
                data = json.loads(self.rfile.read(size))
                self.send(review.answer(data['id'], data['stock'], data.get('comply'), data.get('expected')))
            except (ValueError, KeyError, OSError) as error:
                self.send(dict(error=str(error)), status=400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, default=ROOT / 'labels/silver_labels.txt')
    parser.add_argument('--planogram', type=Path, default=ROOT / 'data/planogram.json')
    parser.add_argument('--images', type=Path, default=ROOT / 'data/images')
    parser.add_argument('--state', type=Path, default=ROOT / 'labels/review/session.json')
    parser.add_argument('--scope', choices=['all', 'empty', 'unsure'], default='all')
    parser.add_argument('--task', choices=['stock', 'both'], default='stock')
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--apply', action='store_true', help='Merge saved answers into source, then exit')
    args = parser.parse_args()
    with session_lock(args.state):
        run(args)


def run(args):
    review = Review(args.labels, args.planogram, args.images, args.state, args.scope, args.task)
    if args.apply:
        backup = review.apply()
        print(f'Applied {len(review.session["answers"])} answers to {review.labels}\nBackup: {backup}')
        return
    # Bind before writing anything: a second default instance fails without touching state.
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(review))
    review.save()
    review.export()
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'{len(review.items)} area-frames. Open {url}\nSession: {review.state}\nCtrl+C to stop.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
