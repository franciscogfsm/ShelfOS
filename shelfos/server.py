"""HTTP API and web app for ShelfOS: one process serves the model and the interface.

    GET  /api/health
    GET  /api/store                       the reference day plus the images analysed in this run
    POST /api/analyze                     multipart "files" (+ "paths"): images and/or zips -> NDJSON stream
    POST /api/analyze-folder              {"path": "..."} -> NDJSON stream
    GET  /api/predictions                 official submission format (?scope=run|all&empty=compliant|noncompliant&download=1)
    POST /api/score                       body = annotations.json -> official score breakdown
    POST /api/policy                      {"emptyCompliant": bool}
    POST /api/reset                       forget the run
    GET  /api/count/policy                which products the "Count units" button may count
    POST /api/count                       {"camera","file","area"} -> visible units with boxes (vision model, on demand)
    GET  /frames/{camera}/{file}          camera image
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .service import ShelfService
from .assistant import DEFAULT_MODEL, config, context_of, stream_chat

NO_UI = """<!doctype html><meta charset="utf-8"><title>ShelfOS</title>
<body style="background:#05070a;color:#e6edf3;font:15px system-ui;padding:48px;line-height:1.6">
<h1>Shelf<span style="color:#2fe0a0">OS</span> engine is running</h1>
<p>The web interface has not been built yet. Run <code>npm install &amp;&amp; npm run build</code> inside <code>web/</code> and reload.</p>
<p>The API is live: <a style="color:#22d3ee" href="/api/health">/api/health</a>, <a style="color:#22d3ee" href="/docs">/docs</a>.</p>"""


def _policy(empty: str | None, default: bool) -> bool:
    if empty is None:
        return default
    return empty.lower() in ("compliant", "true", "1", "yes")


def _ndjson(events):
    for ev in events:
        yield json.dumps(ev, separators=(",", ":")) + "\n"


def create_app(service: ShelfService, ui_dir: str | Path = "web/out") -> FastAPI:
    app = FastAPI(title="ShelfOS", docs_url="/docs", redoc_url=None)
    app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?", allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/health")
    def health():
        return service.health()

    @app.get("/api/store")
    def store():
        return JSONResponse(service.store(), headers={"Cache-Control": "no-store"})

    @app.get('/api/assistant')
    def assistant_status():
        return dict(configured=bool(config('OPENROUTER_API_KEY')), model=config('OPENROUTER_MODEL', DEFAULT_MODEL))

    @app.post('/api/assistant/chat')
    async def assistant_chat(request: Request):
        raw = await request.body()
        if len(raw) > 400000:  # 20 messages of 6000 characters fit; older builds of the app also send their cards back
            raise HTTPException(413, 'Conversation is too long.')
        try:
            body = json.loads(raw)
            messages = body['messages']
            if not isinstance(messages, list) or not 1 <= len(messages) <= 20:
                raise ValueError()
            if any(not isinstance(m, dict) or m.get('role') not in ('user', 'assistant') or
                   not isinstance(m.get('content'), str) or not 0 < len(m['content']) <= 6000 for m in messages):
                raise ValueError()
            if messages[-1]['role'] != 'user':
                raise ValueError()
            selection = body.get('selection', {})
            if not isinstance(selection, dict) or not isinstance(selection.get('completedTasks', []), list):
                raise ValueError()
            messages = [dict(role=m['role'], content=m['content']) for m in messages]
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, 'Invalid conversation.')
        key = config('OPENROUTER_API_KEY')
        if not key:
            raise HTTPException(503, 'Set OPENROUTER_API_KEY in the project .env file to connect ShelfOS AI.')
        context = context_of(service.store(), selection)
        return StreamingResponse(_ndjson(stream_chat(messages, context, key, config('OPENROUTER_MODEL', DEFAULT_MODEL))),
            media_type='application/x-ndjson', headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    # ---- unit counting: on demand, outside the prediction path (shelfos/counting.py) -------------
    @app.get('/api/count/policy')
    def count_policy():
        from .counting import policy
        return policy(service.areas, configured=bool(config('OPENROUTER_API_KEY')))

    @app.post('/api/count')
    async def count(request: Request):
        from .counting import CountError, count_area, countable
        from .engine import official
        try:
            body = json.loads(await request.body())
            camera, file, area_id = (str(body[k]) for k in ('camera', 'file', 'area'))
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400, 'Send {"camera", "file", "area"}.')
        area = next((a for a in service.areas.get(camera, []) if a.area_id == area_id), None)
        path = service.frame_path(camera, file)
        if area is None or path is None:
            raise HTTPException(404, 'No such area or frame.')
        if not countable(area.product_name):
            raise HTTPException(422, 'Not countable from this camera.')
        with service.lock:
            d = service.run.get(camera, {}).get(Path(file).name, {}).get('areas', {}).get(area_id)
        d = d or service.reference.get(camera, {}).get(Path(file).name, {}).get(area_id)
        if d:
            o = official(d, service.empty_compliant)
            if not o['planogram_compliant'] and o['stock_level'] != 'empty':
                raise HTTPException(409, 'This slot holds another product.')
        key = config('OPENROUTER_API_KEY')
        if not key:
            raise HTTPException(503, 'Set OPENROUTER_API_KEY in the project .env file to count units.')
        try:
            return await asyncio.to_thread(count_area, path, camera, file, area, key)
        except CountError as e:
            raise HTTPException(502, str(e))

    @app.post("/api/analyze")
    async def analyze(files: list[UploadFile] = File(...), paths: list[str] = Form(default=[])):
        items = []
        for i, f in enumerate(files):
            rel = paths[i] if i < len(paths) and paths[i] else (f.filename or f"image_{i}.jpg")
            items.append((rel, await f.read()))
        return StreamingResponse(_ndjson(service.analyze_items(items)), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})

    @app.post("/api/analyze-folder")
    async def analyze_folder(request: Request):
        body = await request.json()
        path = str(body.get("path", "")).strip()
        if not path:
            raise HTTPException(400, "path is required")
        return StreamingResponse(_ndjson(service.analyze_folder(path)), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})

    @app.get("/api/predictions")
    def predictions(scope: str = "run", empty: str | None = None, download: int = 0):
        body = json.dumps(service.predictions(scope, _policy(empty, service.empty_compliant)), indent=1)
        headers = {"Cache-Control": "no-store"}
        if download:
            headers["Content-Disposition"] = 'attachment; filename="predictions.json"'
        return Response(body, media_type="application/json", headers=headers)

    @app.post("/api/score")
    async def score(request: Request, empty: str | None = None):
        try:
            annotations = json.loads(await request.body())
        except ValueError:
            raise HTTPException(400, "the body is not valid JSON")
        if not isinstance(annotations, dict) or not all(isinstance(v, dict) for v in annotations.values()):
            raise HTTPException(400, "expected the annotation format {camera: {image: {area: {...}}}}")
        return service.score(annotations, _policy(empty, service.empty_compliant))

    @app.post("/api/policy")
    async def policy(request: Request):
        body = await request.json()
        service.empty_compliant = bool(body.get("emptyCompliant", True))
        return {"emptyCompliant": service.empty_compliant}

    @app.post("/api/reset")
    def reset():
        service.reset()
        return {"ok": True}

    @app.get("/frames/{camera}/{file}")
    def frame(camera: str, file: str):
        p = service.frame_path(camera, file)
        if p is None:
            raise HTTPException(404, "no such frame")
        return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})

    ui = Path(ui_dir)
    if (ui / "index.html").exists():
        @app.get("/colaboradores", include_in_schema=False)
        @app.get("/colaboradores/", include_in_schema=False)
        def collaborators():
            page = ui / "colaboradores.html"
            if not page.exists():
                page = ui / "colaboradores" / "index.html"
            if not page.exists():
                raise HTTPException(404, "Build the web app to open the collaborators demo")
            return FileResponse(page)

        app.mount("/", StaticFiles(directory=ui, html=True), name="ui")
    else:
        @app.get("/")
        def no_ui():
            return HTMLResponse(NO_UI)

    return app
