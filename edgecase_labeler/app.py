"""Independent edge-case label review. Run: python edgecase_labeler/app.py --name marti"""
from __future__ import annotations

import argparse
import copy
import json
import re
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MANIFEST = ROOT / 'ai_generated_edgecases/dataset_large/manifest.json'


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


class Store:
    def __init__(self, name, manifest=MANIFEST, output=HERE / 'output'):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name):
            raise ValueError('Nome: usa apenas letras, números, - ou _.')
        self.name, self.output = name, Path(output)
        self.manifest = json.loads(Path(manifest).read_text(encoding='utf-8'))
        plan = json.loads((ROOT / 'data/planogram.json').read_text(encoding='utf-8'))
        self.areas = {str(cam): [dict(area_id=a['area_id'], product_name=a['product_name'],
                       quad=[a['image_coordinates'][k] for k in ('top_left', 'top_right', 'bottom_right', 'bottom_left')])
                       for a in v['products']] for section in plan.values() for cam, v in section['cameras'].items()}
        self.cases = {c['id']: c for c in self.manifest['cases']}
        self.path = self.output / (name + '_progress.json')
        self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else dict(revision=0, cases={})
        self.lock = threading.Lock()

    def values(self, case):
        saved = self.state['cases'].get(case['id'], {})
        return {a['area_id']: copy.deepcopy(saved.get(a['area_id'], dict(
            stock_level=case.get('labels', {}).get(a['area_id'], {}).get('stock_level'),
            planogram_compliant=case.get('labels', {}).get(a['area_id'], {}).get('planogram_compliant'),
            uncertain=False, reviewed=False, excluded=False, note='')))
            for a in self.areas[str(case['camera'])]}

    def meta(self):
        with self.lock:
            cases = [dict(id=c['id'], camera=c['camera'], scenario=c['scenario'], split=c['split'],
                     image='/image/' + c['id'], areas=self.areas[str(c['camera'])],
                     warning=c.get('exclusion_reason'), initial_source=c.get('annotation_authority', 'Etiquetas propostas locais; ainda sem revisão humana.'),
                     state=self.values(c)) for c in self.cases.values()]
            return dict(name=self.name, revision=self.state['revision'], cases=cases, output=str(self.output))

    def export(self, state):
        reviewed = []
        for case in self.cases.values():
            labels = {}
            for aid, v in state['cases'].get(case['id'], {}).items():
                if v['reviewed'] and not v['excluded'] and not v['uncertain']:
                    labels[aid] = dict(stock_level=v['stock_level'], planogram_compliant=v['planogram_compliant'],
                                       scenario=case['scenario'], note=v['note'], reviewer=self.name, reviewed_at=v['updated_at'])
            if labels:
                reviewed.append(dict(case, labels=labels, reviewed=True, human_reviewed=True,
                                     complete_human_review=len(labels) == len(self.areas[str(case['camera'])])))
        return dict(self.manifest, cases=reviewed, label_authority='Explicit manual confirmations by ' + self.name)

    def save(self, request):
        with self.lock:
            if request.get('revision') != self.state['revision']:
                raise RuntimeError('O progresso mudou noutra janela. Recarrega antes de continuar.')
            cid, aid, v = request['case_id'], request['area_id'], request['value']
            if cid not in self.cases or aid not in {a['area_id'] for a in self.areas[str(self.cases[cid]['camera'])]}:
                raise ValueError('Imagem/área desconhecida.')
            v = {k: v.get(k) for k in ('stock_level', 'planogram_compliant', 'uncertain', 'reviewed', 'excluded', 'note')}
            if v['stock_level'] not in (None, 'empty', 'half', 'full'):
                raise ValueError('Stock inválido.')
            if v['planogram_compliant'] is not None and type(v['planogram_compliant']) is not bool:
                raise ValueError('Conformidade inválida.')
            if any(type(v[k]) is not bool for k in ('uncertain', 'reviewed', 'excluded')) or not isinstance(v['note'], str) or len(v['note']) > 3000:
                raise ValueError('Estado/nota inválido.')
            if v['stock_level'] == 'empty':
                v['planogram_compliant'] = True
            if v['reviewed'] and not v['excluded'] and (v['stock_level'] is None or v['planogram_compliant'] is None or v['uncertain']):
                raise ValueError('Escolhe stock e produto, ou exclui a área com um motivo.')
            if v['excluded'] and not v['note'].strip():
                raise ValueError('Indica o motivo de exclusão.')
            v['updated_at'] = datetime.now(timezone.utc).isoformat()
            state = copy.deepcopy(self.state)
            state['cases'].setdefault(cid, {})[aid] = v
            state['revision'] += 1
            atomic_json(self.path, state)
            self.state = state
            try:
                atomic_json(self.output / (self.name + '_reviewed_manifest.json'), self.export(state))
            except OSError as e:
                return dict(revision=state['revision'], warning='Progresso guardado, mas exportação falhou: ' + str(e))
            return dict(revision=state['revision'])


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def json_response(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            route = unquote(urlparse(self.path).path)
            if route == '/api/meta':
                return self.json_response(store.meta())
            if route == '/api/export':
                with store.lock:
                    return self.json_response(store.export(store.state))
            if route in ('/', '/index.html'):
                path = HERE / 'index.html'
            elif route.startswith('/image/') and route[7:] in store.cases:
                path = (ROOT / store.cases[route[7:]]['image']).resolve()
                if not path.is_relative_to((ROOT / 'ai_generated_edgecases').resolve()):
                    return self.json_response(dict(error='Imagem fora do dataset.'), 400)
            else:
                return self.json_response(dict(error='Não encontrado.'), 404)
            data = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8' if path.suffix == '.html' else 'image/png' if path.suffix == '.png' else 'image/jpeg')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache' if path.suffix == '.html' else 'private, max-age=3600')
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != '/api/label':
                return self.json_response(dict(error='Não encontrado.'), 404)
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 16000:
                    raise ValueError('Pedido inválido.')
                return self.json_response(store.save(json.loads(self.rfile.read(length))))
            except RuntimeError as e:
                return self.json_response(dict(error=str(e)), 409)
            except (ValueError, KeyError, TypeError) as e:
                return self.json_response(dict(error=str(e)), 400)
            except OSError as e:
                return self.json_response(dict(error='Não foi possível guardar: ' + str(e)), 500)

        def log_message(self, *_):
            pass
    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--name', default='marti')
    ap.add_argument('--port', type=int, default=8767)
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args()
    store = Store(args.name)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(store))
    url = f'http://127.0.0.1:{args.port}'
    print(f'Edge-case labeler: {url}\nProgresso: {store.path}\nCtrl+C para sair.', flush=True)
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
