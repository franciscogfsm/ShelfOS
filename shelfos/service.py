"""Everything between an image file and the answer: decode, find the camera, embed, predict,
and keep the run so it can be shown, exported in the official format and scored."""
from __future__ import annotations

import io
import json
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path

import cv2
import numpy as np

from .bank import thumbs_of
from .engine import OBSTRUCT_FROM, Engine, official
from .features import MODEL_NAME, Embedder
from .planogram import Area, load_planogram
from .scoring import score_submission, stock_points

IMAGE_EXT = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".bmp", ".webp", ".tif", ".tiff", ".jp2"}  # same set in validate.py
_SMALL = {"CNT", "KG", "IMP", "CAT", "I", "EMB.", "EMB", "SC", "INT", "R0", "CAL", "CAL.", "IGP", "P/", "S/", "A/AA", "A/AA/AAA", "EMB:."}
MIN_VISIBLE = 0.15  # an area with less of its quad inside the frame is answered from memory


def display_name(name: str) -> str:
    """'BANANA CAT I CNT KG' -> 'Banana'; keeps pack sizes and varieties, drops catalogue codes."""
    words = [w for w in name.split() if w.upper() not in _SMALL and "/" not in w]
    return " ".join(w if any(ch.isdigit() for ch in w) else w.capitalize() for w in words) or name.title()


def is_image(name: str) -> bool:
    p = Path(name)
    return p.suffix.lower() in IMAGE_EXT and not p.name.startswith("._") and "__MACOSX" not in name


def timestamp_of(name: str) -> int | None:
    """Capture time from a file name such as 1751052241.jpg (also when it carries a prefix)."""
    m = re.search(r"(?<!\d)(1[5-9]\d{8})(?!\d)", Path(name).stem)
    return int(m.group(1)) if m else None


def _zip_bytes(zf: zipfile.ZipFile, name: str) -> bytes:
    """One member of a zip; b"" when it cannot be read (encrypted, corrupt), which is then handled like an unreadable image."""
    try:
        return zf.read(name)
    except Exception:
        return b""


class ShelfService:
    def __init__(self, model_path="models/engine.pkl", planogram_path="data/planogram.json", reference_path="models/reference_day.json",
                 reference_images="data/images", run_dir="runs/latest", device: str | None = None, empty_compliant: bool = True):
        t0 = time.time()
        self.areas: dict[str, list[Area]] = load_planogram(planogram_path)
        self.engine = Engine.load(model_path)
        self.engine.empty_compliant = empty_compliant
        self.embedder = Embedder(self.engine.model_name or MODEL_NAME, device=device, size=self.engine.crop_size, tta=getattr(self.engine, "tta", False))
        self.embedder.warmup()
        fh, fw = self.engine.frame_size[1], self.engine.frame_size[0]
        self.hidden = {cam: [i for i, a in enumerate(areas) if a.visible_fraction((fh, fw)) < MIN_VISIBLE] for cam, areas in self.areas.items()}
        self.reference_images = Path(reference_images)
        self.reference: dict = json.loads(Path(reference_path).read_text(encoding="utf-8")) if reference_path and Path(reference_path).is_file() else {}
        self.run_dir = Path(run_dir)
        self.run: dict[str, dict[str, dict]] = {}
        self.lock = threading.Lock()
        self.model_lock = threading.Lock()
        self._reference_frames: dict = {}  # policy -> {camera: {file: frame json}}, built once
        self._load_run()
        self.load_seconds = time.time() - t0

    # ---- policy ---------------------------------------------------------------------------
    @property
    def empty_compliant(self) -> bool:
        return self.engine.empty_compliant

    @empty_compliant.setter
    def empty_compliant(self, value: bool) -> None:
        self.engine.empty_compliant = bool(value)

    # ---- one image ------------------------------------------------------------------------
    def resolve_camera(self, rel_path: str, image: np.ndarray | None) -> tuple[str | None, str | None, list[str]]:
        """Camera of an image: its folder name, else a camera id in the file name, else the picture itself."""
        warnings: list[str] = []
        parts = [p for p in re.split(r"[\\/]+", rel_path) if p]
        named = next((p for p in reversed(parts[:-1]) if p in self.areas), None)
        source = "folder" if named else None
        if named is None and parts:
            hits = [c for c in re.findall(r"(?<!\d)(\d{3,6})(?!\d)", Path(parts[-1]).stem) if c in self.areas]
            if len(set(hits)) == 1:
                named, source = hits[0], "name"
        if named is None:  # a folder that carries the id among other text: cam_6215
            for p in reversed(parts[:-1]):
                hits = {c for c in re.findall(r"(?<!\d)(\d{3,6})(?!\d)", p) if c in self.areas}
                if len(hits) == 1:
                    named, source = hits.pop(), "folder"
                    break
        seen, sim, margin = (None, 0.0, 0.0)
        if image is not None and self.engine.cameras is not None:
            seen, sim, margin = self.engine.cameras.identify(image)
        if named:
            if seen and seen != named and sim > 0.6 and margin > 0.1:
                warnings.append(f"filed under camera {named} but the picture looks like camera {seen}")
            return named, source, warnings
        if seen is None:
            return None, None, ["no camera folder and the image could not be read"]
        if sim < 0.45 or margin < 0.02:
            warnings.append(f"camera recognised from the picture with low confidence ({sim:.2f})")
        return seen, "auto", warnings

    def _fit_frame(self, image: np.ndarray, warnings: list[str]) -> np.ndarray:
        """The planogram is in the pixel grid of the reference frames; bring any other size onto it."""
        w, h = self.engine.frame_size
        ih, iw = image.shape[:2]
        if (iw, ih) != (w, h):
            if abs(iw / ih - w / h) > 0.02:
                warnings.append(f"unexpected aspect ratio {iw}x{ih}; stretched to {w}x{h}")
            else:
                warnings.append(f"resized from {iw}x{ih} to {w}x{h}")
            image = cv2.resize(image, (w, h), interpolation=cv2.INTER_AREA if iw > w else cv2.INTER_LINEAR)
        return image

    def predict_image(self, image: np.ndarray, camera: str, file_name: str) -> list[dict]:
        areas = self.areas[camera]
        crops = [self.embedder.crop(image, a) for a in areas]
        with self.model_lock:
            glob, patches = self.embedder.embed(crops, compact=False)
        details = self.engine.predict(glob, patches, thumbs_of(crops), areas, fname=file_name)
        hidden = self.hidden.get(camera)
        if hidden:
            memory = self.engine.fallback([areas[i] for i in hidden])
            for i, d in zip(hidden, memory):
                details[i] = d
        return details

    def analyze(self, data: bytes | None, rel_path: str, save: bool = True) -> dict:
        """Analyse one image -> event dict ({"type": "frame", ...} or {"type": "skip", ...})."""
        t0 = time.perf_counter()
        name = Path(rel_path.replace("\\", "/")).name
        image = None
        if data:
            try:
                image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)  # 8-bit BGR whatever the file holds
            except cv2.error:
                image = None
        camera, source, warnings = self.resolve_camera(rel_path, image)
        if camera is None:
            return {"type": "skip", "file": rel_path, "reason": "; ".join(warnings) or "unknown camera"}
        if camera not in self.areas:
            return {"type": "skip", "file": rel_path, "reason": f"camera {camera} is not in the planogram"}
        if image is None:
            warnings.append("image could not be read; answered from the last known state of each area")
            details = self.engine.fallback(self.areas[camera])
        else:
            try:
                image = self._fit_frame(image, warnings)
                details = self.predict_image(image, camera, name)
            except Exception as e:  # a missing area costs 5 points; the last known state does not
                warnings.append(f"image could not be analysed ({type(e).__name__}); answered from the last known state of each area")
                details = self.engine.fallback(self.areas[camera])
            blocked = [a.area_id for a, d in zip(self.areas[camera], details) if d.get("obstruction", 0) >= OBSTRUCT_FROM]
            if blocked:
                warnings.append(f"{len(blocked)} area(s) partly hidden by something new on the shelf (shopper, cart, boxes): {', '.join(blocked[:6])}"
                                f"{'...' if len(blocked) > 6 else ''}; answered on the low side")
        ts = timestamp_of(name)
        if ts is None:
            ts = self._next_ts(camera)
            warnings.append("no capture time in the file name; placed after the latest known frame")
        ms = int(round((time.perf_counter() - t0) * 1000))
        record = {"camera": camera, "file": name, "ts": ts, "ms": ms, "cameraSource": source, "warnings": warnings,
                  "areas": {a.area_id: d for a, d in zip(self.areas[camera], details)}}
        with self.lock:
            self.run.setdefault(camera, {})[name] = record
            if save:
                dst = self.run_dir / "frames" / camera / name
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if data:
                        dst.write_bytes(data)
                except OSError:  # the copy is only for display; the answer is already in the run
                    pass
        return {"type": "frame", "camera": camera, "file": name, "ms": ms, "cameraSource": source, "warnings": warnings, "frame": self._frame_json(record, "run")}

    def _next_ts(self, camera: str) -> int:
        known = [ts for ts in (timestamp_of(f) for f in self.reference.get(camera, {})) if ts]
        known += [r["ts"] for r in self.run.get(camera, {}).values()]
        return (max(known) if known else int(time.time())) + 3600

    # ---- many images ----------------------------------------------------------------------
    def analyze_items(self, items):
        """items: iterable of (relative path, bytes). Zips are opened in place. Yields events."""
        t0 = time.perf_counter()
        n_img = n_area = 0
        for rel, data in items:
            if rel.lower().endswith(".zip"):
                try:
                    zf = zipfile.ZipFile(io.BytesIO(data))
                except zipfile.BadZipFile:
                    yield {"type": "skip", "file": rel, "reason": "not a readable zip file"}
                    continue
                inner = sorted(n for n in zf.namelist() if not n.endswith("/"))
                members = [(n, _zip_bytes(zf, n)) for n in inner if is_image(n)]
                for n in inner:
                    if not is_image(n) and "__MACOSX" not in n and not Path(n).name.startswith("."):
                        yield {"type": "skip", "file": n, "reason": "not an image"}
            elif is_image(rel):
                members = [(rel, data)]
            else:
                if not Path(rel).name.startswith("."):
                    yield {"type": "skip", "file": rel, "reason": "not an image"}
                continue
            for n, d in members:
                ev = self.analyze(d, n)
                if ev["type"] == "frame":
                    n_img += 1
                    n_area += len(ev["frame"]["areas"])
                yield ev
        self._save_run()
        yield {"type": "done", "images": n_img, "areas": n_area, "ms": int(round((time.perf_counter() - t0) * 1000))}

    def analyze_folder(self, folder: str):
        root = Path(folder.strip().strip('"'))
        if not root.exists():
            yield {"type": "error", "message": f"folder not found: {root}"}
            return
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())

        def items():
            for p in files:
                rel = p.name if root.is_file() else str(Path(root.name) / p.relative_to(root))
                if is_image(p.name) or p.suffix.lower() == ".zip":
                    try:
                        yield rel, p.read_bytes()
                    except OSError:
                        yield rel, b""

        yield from self.analyze_items(items())

    # ---- the run --------------------------------------------------------------------------
    def reset(self) -> None:
        with self.lock:
            self.run = {}
            shutil.rmtree(self.run_dir, ignore_errors=True)

    def _save_run(self) -> None:
        with self.lock:
            try:
                self.run_dir.mkdir(parents=True, exist_ok=True)
                (self.run_dir / "run.json").write_text(json.dumps(self.run), encoding="utf-8")
            except OSError:  # the run stays in memory, which is what predictions() reads
                pass

    def _load_run(self) -> None:
        f = self.run_dir / "run.json"
        if f.exists():
            try:
                self.run = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.run = {}

    def frame_path(self, camera: str, file_name: str) -> Path | None:
        name = Path(file_name).name
        if camera not in self.areas:
            return None
        for p in (self.run_dir / "frames" / camera / name, self.reference_images / camera / name):
            if p.is_file():
                return p
        return None

    # ---- views ----------------------------------------------------------------------------
    def _area_json(self, d: dict) -> dict:
        return {
            "ok": d["p_compliant"] >= 0.5,
            "level": d["stock_level"],
            "probs": [round(x, 3) for x in d["stock_probs"]],
            "pOk": round(d["p_compliant"], 3),
            "occ": round(d["occupancy"], 3),
            "map": [[round(v, 1) for v in row] for row in d["occupancy_map"]],
            "looks": d.get("looks_like", []),
            "obstruction": round(float(d.get("obstruction", 0.0)), 3),
            "source": d.get("source", "image"),
            "official": official(d, self.empty_compliant),
        }

    def _frame_json(self, record: dict, origin: str) -> dict:
        return {"file": record["file"], "ts": record["ts"], "origin": origin, "ms": record.get("ms"), "cameraSource": record.get("cameraSource"),
                "warnings": record.get("warnings", []), "areas": {aid: self._area_json(d) for aid, d in record["areas"].items()}}

    def _reference(self, cam: str) -> dict:
        cache = self._reference_frames.setdefault(self.empty_compliant, {})
        if cam not in cache:
            cache[cam] = {fname: self._frame_json({"file": fname, "ts": timestamp_of(fname), "areas": per_area}, "reference")
                          for fname, per_area in self.reference.get(cam, {}).items() if timestamp_of(fname) is not None}
        return cache[cam]

    def store(self) -> dict:
        products, cameras = {}, []
        with self.lock:
            run = {cam: dict(files) for cam, files in self.run.items()}
        for cam, areas in self.areas.items():
            for a in areas:
                products[a.product_id] = {"name": display_name(a.product_name), "rawName": a.product_name}
            frames = dict(self._reference(cam))
            for fname, record in run.get(cam, {}).items():
                frames[fname] = self._frame_json(record, "run")
            if not frames:
                continue
            cameras.append({
                "id": cam,
                "areas": [{"id": a.area_id, "productId": a.product_id, "product": display_name(a.product_name), "rawName": a.product_name,
                           "quad": [[round(float(x), 1), round(float(y), 1)] for x, y in a.quad]} for a in areas],
                "frames": sorted(frames.values(), key=lambda f: f["ts"]),
            })
        n_img = sum(len(v) for v in run.values())
        return {
            "store": "Continente Bom Dia S. Romão, Leiria", "section": "Frutas e Legumes",
            "width": self.engine.frame_size[0], "height": self.engine.frame_size[1],
            "emptyCompliant": self.empty_compliant, "products": products, "cameras": cameras,
            "run": {"images": n_img, "areas": sum(len(r["areas"]) for v in run.values() for r in v.values()),
                    "ms": sum(r.get("ms") or 0 for v in run.values() for r in v.values())} if n_img else None,
        }

    def predictions(self, scope: str = "run", empty_compliant: bool | None = None) -> dict:
        """Official nested format {camera: {image file: {area_id: {planogram_compliant, stock_level, stock_value}}}}."""
        policy = self.empty_compliant if empty_compliant is None else empty_compliant
        out: dict = {}
        if scope == "all":
            for cam, files in self.reference.items():
                for fname, per_area in files.items():
                    out.setdefault(cam, {})[fname] = {aid: official(d, policy) for aid, d in per_area.items()}
        with self.lock:
            for cam, files in self.run.items():
                for fname, record in files.items():
                    out.setdefault(cam, {})[fname] = {aid: official(d, policy) for aid, d in record["areas"].items()}
        return out

    def score(self, annotations: dict, empty_compliant: bool | None = None) -> dict:
        """Official score of the current run against an annotation file, with the list of mistakes."""
        pred = self.predictions("all", empty_compliant)
        res = score_submission(pred, annotations)
        mistakes = []
        for cam, images in annotations.items():
            for fname, areas in images.items():
                for aid, t in areas.items():
                    p = pred.get(cam, {}).get(fname, {}).get(aid)
                    if p is None:
                        mistakes.append({"camera": cam, "file": fname, "area": aid, "field": "missing", "predicted": None, "truth": t, "points": -5})
                        continue
                    if bool(p["planogram_compliant"]) != bool(t["planogram_compliant"]):
                        mistakes.append({"camera": cam, "file": fname, "area": aid, "field": "id", "predicted": p["planogram_compliant"], "truth": t["planogram_compliant"], "points": -2})
                    s = stock_points(float(p["stock_value"]), float(t["stock_value"]))
                    if s != 1:
                        mistakes.append({"camera": cam, "file": fname, "area": aid, "field": "stock", "predicted": p["stock_level"], "truth": t["stock_level"], "points": s})
        res["mistakes"] = mistakes
        return res

    def health(self) -> dict:
        return {"ready": True, "device": self.embedder.device, "model": self.embedder.model_name, "cameras": len(self.areas),
                "areas": sum(len(v) for v in self.areas.values()), "emptyCompliant": self.empty_compliant, "loadSeconds": round(self.load_seconds, 1)}
