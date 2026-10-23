"""Ferramenta de revisão de labels. Só biblioteca standard, nada para instalar.

    python3 labeler/app.py --name rodrigo                # abre http://localhost:8765
    python3 labeler/app.py --merge rodrigo francisco     # junta pessoas -> output/merged_annotations.json
    python3 labeler/app.py --apply rodrigo francisco     # escreve as áreas revistas em labels/silver_labels.txt

Cada área vem pré-preenchida de labels/silver_labels.txt (ou --prefill). Só
corriges o que está mal. O output oficial é reescrito a cada alteração em
labeler/output/<nome>_annotations.json.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DATASET = REPO / "dataset"
ZIP = DATASET / "Frutas e Legumes (train & test).zip"
PLANOGRAM = DATASET / "planogram.json"
SILVER = REPO / "labels" / "silver_labels.txt"  # fonte de treino do modelo (shelfos)
IMAGES = HERE / "data" / "images"  # gitignored
BACKUPS = HERE / "backups"  # gitignored
LABELS = HERE / "labels"  # progresso de cada pessoa (commit)
OUTPUT = HERE / "output"  # ficheiros no formato oficial (commit)

# Divisão do trabalho: câmaras ordenadas, 7 primeiras para um, 7 últimas para o outro.
TEAM = {"rodrigo": 0, "francisco": 1}

LEVELS = {"empty": 0, "half": 0.5, "full": 1}
SILVER_STOCK = {"E": "empty", "H": "half", "F": "full"}


# ---------- dados ----------

def ensure_images() -> None:
    if IMAGES.exists() and any(IMAGES.iterdir()):
        return
    print(f"A extrair imagens para {IMAGES} ...")
    IMAGES.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP) as z:
        for info in z.infolist():
            parts = Path(info.filename).parts
            if info.is_dir() or parts[0] == "__MACOSX" or len(parts) != 3:
                continue
            _, cam, fname = parts
            if not (cam.isdigit() and fname.endswith(".jpg") and not fname.startswith(".")):
                continue
            dst = IMAGES / cam / fname
            dst.parent.mkdir(exist_ok=True)
            dst.write_bytes(z.read(info))


def load_planogram() -> dict[str, list[dict]]:
    cams = json.loads(PLANOGRAM.read_text())["Frutas e Legumes"]["cameras"]
    return {
        cam: [
            {
                "area_id": a["area_id"],
                "product_name": a["product_name"],
                "quad": [a["image_coordinates"][k] for k in ("top_left", "top_right", "bottom_right", "bottom_left")],
            }
            for a in v["products"]
        ]
        for cam, v in cams.items()
    }


def list_frames(planogram) -> dict[str, list[str]]:
    return {cam: sorted(p.name for p in (IMAGES / cam).glob("*.jpg")) for cam in planogram}


def read_silver() -> dict[str, tuple[str, str]]:
    """{area_id: (stock_chars, comply_chars)} tal como estão no ficheiro."""
    return read_silver_text(SILVER.read_text(encoding="utf-8-sig")) if SILVER.exists() else {}


def read_silver_text(text: str) -> dict[str, tuple[str, str]]:
    out = {}
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            area, stock, comply = (p.strip() for p in line.split("|"))
            out[area] = (stock, comply)
    return out


def from_silver(stock: str, comply: str, frames: list[str]) -> dict:
    """Silver: E/H/F stock, T/F/N produto, minúscula = incerto, ? = não dá para ver."""
    return {
        f: {
            "stock": SILVER_STOCK.get(s.upper(), "half"),
            "compliant": c.upper() != "F",  # N = nada para avaliar -> conforme
            "unsure": s.islower() or c.islower() or c == "?",
            "unknown": s.upper() not in SILVER_STOCK,
        }
        for f, s, c in zip(frames, stock, comply)
    }


def to_silver(frames: dict, order: list[str], base: tuple[str, str] | None = None) -> tuple[str, str]:
    """Inverso de from_silver. Fotos que não mudaram face a `base` mantêm os carateres originais."""
    old = from_silver(*base, order) if base and len(base[0]) == len(order) else {}
    stock, comply = "", ""
    for t, f in enumerate(order):
        v = frames[f]
        if f in old and old[f] == {k: v.get(k, False) for k in old[f]}:
            stock, comply = stock + base[0][t], comply + base[1][t]
            continue
        s = "?" if v.get("unknown") else v["stock"][0].upper()
        c = "F" if not v["compliant"] else ("N" if v["stock"] == "empty" or v.get("unknown") else "T")
        if v["unsure"]:
            s, c = s.lower(), c.lower()
        stock, comply = stock + s, comply + c
    return stock, comply


def json_prefill(path: Path) -> dict:
    """Lê um ficheiro no formato oficial (ex.: previsões do modelo)."""
    out: dict = {}
    for imgs in json.loads(path.read_text()).values():
        for img, areas in imgs.items():
            for area, v in areas.items():
                out.setdefault(area, {})[img] = {
                    "stock": v["stock_level"],
                    "compliant": bool(v["planogram_compliant"]),
                    "unsure": bool(v.get("unsure", False)),
                    "unknown": False,
                }
    return out


def default_label():
    return {"stock": "half", "compliant": True, "unsure": True, "unknown": False}


def assigned_cameras(name: str, cameras: list[str], override: str | None) -> list[str]:
    """--cameras ganha; senão a metade do TEAM; nomes desconhecidos veem todas."""
    if override:
        if override == "all":
            return cameras
        wanted = [c.strip() for c in override.split(",")]
        unknown = set(wanted) - set(cameras)
        if unknown:
            raise SystemExit(f"câmaras desconhecidas: {sorted(unknown)}")
        return [c for c in cameras if c in wanted]
    half = len(cameras) // 2
    part = TEAM.get(name.lower())
    if part is None:
        return cameras
    return cameras[:half] if part == 0 else cameras[half:]


def read_opinion(path: Path, frames) -> dict:
    """Segunda opinião (formato silver) -> {area: {frame: {stock|None, compliant, unsure}}}."""
    out = {}
    for area, (stock, comply) in read_silver_text(path.read_text(encoding="utf-8-sig")).items():
        fs = frames.get(area.split("_")[0], [])
        if len(stock) != len(fs):
            print(f"aviso: {area} na opinião não bate com o nº de imagens, ignorado")
            continue
        out[area] = {
            f: {"stock": SILVER_STOCK.get(s.upper()), "compliant": c.upper() != "F", "unsure": s.islower() or c.islower()}
            for f, s, c in zip(fs, stock, comply)
        }
    return out


def disagrees(op: dict, v: dict) -> bool:
    return (op["stock"] is not None and op["stock"] != v["stock"]) or op["compliant"] != v["compliant"]


class Store:
    def __init__(self, name: str, prefill: Path | None, cameras: str | None = None, opinion: Path | None = None):
        ensure_images()
        self.name = name
        self.planogram = load_planogram()
        self.cameras = assigned_cameras(name, sorted(self.planogram), cameras)
        self.frames = list_frames(self.planogram)
        self.silver = read_silver()
        if prefill:
            self.prefill, self.prefill_source = json_prefill(prefill), prefill.name
        else:
            self.prefill, self.prefill_source = {}, "silver_labels.txt" if self.silver else "nada (tudo 'half')"
            for cam, areas in self.planogram.items():
                for a in areas:
                    s = self.silver.get(a["area_id"])
                    if s and len(s[0]) == len(s[1]) == len(self.frames[cam]):
                        self.prefill[a["area_id"]] = from_silver(*s, self.frames[cam])
                    elif s:
                        print(f"aviso: {a['area_id']} no silver não bate com o nº de imagens, ignorado")
        self.path = LABELS / f"{name}.json"
        self.saved = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.lock = threading.Lock()
        # modo --resolver: só as áreas onde a segunda opinião discorda (ou que já resolveste)
        self.opinion = read_opinion(opinion, self.frames) if opinion else None
        self.resolver_areas = None
        if self.opinion is not None:
            self.resolver_areas = {
                a for a, op in self.opinion.items()
                if a.split("_")[0] in self.cameras and (
                    self.saved.get(a, {}).get("resolved")
                    or any(disagrees(op[f], v) for f, v in self.area_state(a.split("_")[0], a)["frames"].items())
                )
            }

    def area_state(self, cam: str, area: str) -> dict:
        if area in self.saved:
            return self.saved[area]
        pre = self.prefill.get(area, {})
        return {"reviewed": False, "frames": {f: pre.get(f, default_label()) for f in self.frames[cam]}}

    def meta(self) -> dict:
        keep = (lambda a: a in self.resolver_areas) if self.resolver_areas is not None else (lambda a: True)
        cameras = []
        for cam, areas in self.planogram.items():
            shown = [
                dict(a, state=self.area_state(cam, a["area_id"]),
                     opinion=self.opinion.get(a["area_id"]) if self.opinion else None)
                for a in areas if keep(a["area_id"])
            ]
            if cam in self.cameras and shown:
                cameras.append({"id": cam, "frames": self.frames[cam], "areas": shown})
        return {
            "name": self.name,
            "prefill_source": self.prefill_source,
            "resolver": self.opinion is not None,
            "cameras": cameras,
        }

    def update(self, area: str, state: dict) -> dict:
        cam = area.split("_")[0]
        if cam not in self.planogram or area not in {a["area_id"] for a in self.planogram[cam]}:
            raise ValueError(f"área desconhecida: {area}")
        frames = {}
        for f in self.frames[cam]:
            v = state["frames"][f]
            if v["stock"] not in LEVELS:
                raise ValueError(f"stock inválido: {v['stock']}")
            frames[f] = {k: bool(v.get(k)) for k in ("compliant", "unsure", "unknown")} | {"stock": v["stock"]}
        with self.lock:
            # relê do disco: o modo normal e o --resolver podem estar abertos ao mesmo tempo
            if self.path.exists():
                self.saved = json.loads(self.path.read_text())
            prev = self.saved.get(area, {})
            # "base" = como o silver estava quando começaste: serve para detetar conflitos no --apply
            base = prev.get("base") or self.silver.get(area)
            self.saved[area] = {"reviewed": bool(state["reviewed"]), "base": base, "frames": frames}
            if state.get("resolved") or prev.get("resolved"):
                self.saved[area]["resolved"] = True
            write_json(self.path, self.saved)
            return self.export()

    def export(self) -> dict:
        full, reviewed = build_annotations(self.planogram, self.frames, self.area_state)
        write_json(OUTPUT / f"{self.name}_annotations.json", full)
        write_json(OUTPUT / f"{self.name}_annotations_reviewed.json", reviewed)
        n_rev = sum(1 for v in self.saved.values() if v["reviewed"])
        return {"reviewed_areas": n_rev, "total_areas": sum(len(a) for a in self.planogram.values())}


def build_annotations(planogram, frames, state_of):
    """Devolve (todas as áreas, só as revistas), no formato exato de annotations.json."""
    full: dict = {}
    reviewed: dict = {}
    for cam, areas in planogram.items():
        for f in frames[cam]:
            for a in areas:
                st = state_of(cam, a["area_id"])
                v = st["frames"][f]
                entry = {
                    "planogram_compliant": bool(v["compliant"]),
                    "stock_level": v["stock"],
                    "stock_value": LEVELS[v["stock"]],
                }
                full.setdefault(cam, {}).setdefault(f, {})[a["area_id"]] = entry
                if st["reviewed"]:
                    reviewed.setdefault(cam, {}).setdefault(f, {})[a["area_id"]] = entry
    return full, reviewed


def write_json(path: Path, obj) -> None:
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=1))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")  # sem conversão de \n no Windows
    os.replace(tmp, path)


# ---------- várias pessoas ----------

def reviewed_states(names: list[str]) -> tuple[dict, int]:
    """{area: estado} das áreas revistas; se duas pessoas reviram a mesma área ganha a primeira."""
    out, conflicts = {}, 0
    for n in names:
        path = LABELS / f"{n}.json"
        if not path.exists():
            raise SystemExit(f"não existe {path}")
        for area, st in json.loads(path.read_text()).items():
            if not st["reviewed"]:
                continue
            if area in out:
                conflicts += out[area]["frames"] != st["frames"]
            else:
                out[area] = st
    return out, conflicts


def merge(names: list[str], prefill: Path | None) -> None:
    base = Store(names[0], prefill)
    rev, conflicts = reviewed_states(names)
    full, reviewed = build_annotations(
        base.planogram, base.frames, lambda c, a: rev.get(a) or dict(base.area_state(c, a), reviewed=False)
    )
    write_json(OUTPUT / "merged_annotations.json", full)
    write_json(OUTPUT / "merged_annotations_reviewed.json", reviewed)
    print(f"merged -> {OUTPUT / 'merged_annotations.json'}: {len(rev)} áreas revistas, "
          f"{conflicts} com desacordo (ganhou {names[0]})")


def apply(names: list[str]) -> None:
    """Escreve as áreas revistas em labels/silver_labels.txt (a fonte de treino), com backup."""
    ensure_images()
    frames = list_frames(load_planogram())
    rev, _ = reviewed_states(names)
    original = SILVER.read_text(encoding="utf-8-sig")
    lines, changed, conflicts = [], 0, []
    for line in original.splitlines(keepends=True):
        if not line.strip() or line.lstrip().startswith("#"):
            lines.append(line)
            continue
        parts = line.rstrip("\r\n").split("|")
        area = parts[0].strip()
        cur = (parts[1].strip(), parts[2].strip())
        if area in rev:
            base = tuple(rev[area]["base"]) if rev[area].get("base") else cur
            new = to_silver(rev[area]["frames"], frames[area.split("_")[0]], base)
            if cur not in (base, new):
                conflicts.append(area)  # alguém mudou esta área no silver depois de começares
            elif cur != new:
                parts[1], parts[2] = f" {new[0]} ", f" {new[1]}"
                changed += 1
        lines.append("|".join(parts) + line[len(line.rstrip("\r\n")):])
    if conflicts:
        raise SystemExit(f"{len(conflicts)} áreas mudaram no silver entretanto, nada foi escrito: {conflicts}")
    bom = "﻿" if SILVER.read_bytes().startswith(b"\xef\xbb\xbf") else ""  # manter o ficheiro igual byte a byte
    backup = BACKUPS / f"silver_labels-{datetime.now():%Y%m%d-%H%M%S}.txt"
    write_text(backup, bom + original)
    write_text(SILVER, bom + "".join(lines))
    after, before = read_silver(), dict(read_silver_text(original))
    for area, st in rev.items():  # confirma que ficou escrito o que reviste
        assert after[area] == to_silver(st["frames"], frames[area.split("_")[0]], tuple(st.get("base") or before[area])), area
    assert set(after) == set(before)
    print(f"{changed} áreas atualizadas em {SILVER} ({len(rev)} revistas). Backup: {backup}")


# ---------- servidor ----------

def make_handler(store: Store):
    index = (HERE / "index.html").read_bytes()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body: bytes, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self.send(200, index, "text/html; charset=utf-8")
            if self.path == "/api/meta":
                return self.send(200, json.dumps(store.meta()).encode())
            if self.path.startswith("/img/"):
                parts = self.path.split("/")
                if len(parts) == 4 and parts[2].isdigit() and parts[3].endswith(".jpg") and parts[3][:-4].isdigit():
                    p = IMAGES / parts[2] / parts[3]
                    if p.exists():
                        return self.send(200, p.read_bytes(), "image/jpeg")
            self.send(404, b"not found", "text/plain")

        def do_POST(self):
            if self.path != "/api/area":
                return self.send(404, b"not found", "text/plain")
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.send(200, json.dumps(store.update(body["area_id"], body["state"])).encode())
            except Exception as e:  # noqa: BLE001
                self.send(400, json.dumps({"error": str(e)}).encode())

    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", help="o teu nome (cada pessoa tem o seu ficheiro)")
    ap.add_argument("--prefill", type=Path, help="JSON no formato oficial para pré-preencher (em vez do silver)")
    ap.add_argument("--cameras", help="ex.: 6215,6371 ou 'all' (por defeito: a tua metade, ver TEAM)")
    ap.add_argument("--resolver", nargs="?", type=Path, const=HERE / "data" / "claude_opinion.txt",
                    help="só as áreas onde a segunda opinião discorda (porta 8766 por defeito)")
    ap.add_argument("--port", type=int)
    ap.add_argument("--merge", nargs="+", metavar="NOME", help="junta labels/<nome>.json de várias pessoas")
    ap.add_argument("--apply", nargs="+", metavar="NOME", help="escreve as áreas revistas em labels/silver_labels.txt")
    args = ap.parse_args()

    if args.merge:
        return merge(args.merge, args.prefill)
    if args.apply:
        return apply(args.apply)
    if not args.name:
        ap.error("--name é obrigatório")
    if args.resolver and not args.resolver.exists():
        raise SystemExit(f"não existe {args.resolver}")
    store = Store(args.name, args.prefill, args.cameras, args.resolver)
    port = args.port or (8766 if args.resolver else 8765)
    print(store.export())
    n_areas = sum(len(store.planogram[c]) for c in store.cameras)
    print(f"{args.name}: {len(store.cameras)} câmaras ({', '.join(store.cameras)}), {n_areas} áreas")
    if args.resolver:
        print(f"modo resolver: {len(store.resolver_areas)} áreas com desacordo ({args.resolver.name})")
    else:
        print(f"pré-preenchido com: {store.prefill_source}")
    print(f"abre http://localhost:{port}  (Ctrl+C para sair; tudo é guardado a cada tecla)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), make_handler(store)).serve_forever()


if __name__ == "__main__":
    main()
