"""Edge-case drill for the ShelfOS service: awkward inputs must still give a complete answer.

usage: python tools/selftest.py [--cpu]

Uses frames of the reference day as stand-ins for new images. Checks behaviour, not accuracy.
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelfos.planogram import list_images, read_image  # noqa: E402
from shelfos.service import ShelfService  # noqa: E402

OFFICIAL = {"planogram_compliant", "stock_level", "stock_value"}
failures = []


def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{f'  ({detail})' if detail else ''}")
    if not ok:
        failures.append(name)


def complete(service, ev):
    """The event answers every planogram area of its camera, in the official vocabulary."""
    areas = {a.area_id for a in service.areas[ev["camera"]]}
    got = ev["frame"]["areas"]
    return set(got) == areas and all(set(v["official"]) == OFFICIAL and v["official"]["stock_level"] in ("empty", "half", "full") for v in got.values())


def main():
    service = ShelfService(reference_path=None, run_dir="runs/selftest", device="cpu" if "--cpu" in sys.argv else None)
    service.reset()
    images = list_images("data/images")
    cams = list(images)
    sample = {cam: images[cam][-1] for cam in cams}
    one = sample[cams[0]]
    raw = one.read_bytes()

    print("camera from the folder name")
    ev = service.analyze(raw, f"{cams[0]}/{one.name}")
    check("answers every area", ev["type"] == "frame" and complete(service, ev))
    check("camera taken from the folder", ev["cameraSource"] == "folder" and ev["camera"] == cams[0])
    check("keeps the file name as the key", ev["file"] == one.name)

    print("loose files: the camera is recognised from the picture")
    hits = 0
    for cam, f in sample.items():
        ev = service.analyze(f.read_bytes(), f.name)
        hits += ev["type"] == "frame" and ev["camera"] == cam and ev["cameraSource"] == "auto" and complete(service, ev)
    check("all cameras recognised", hits == len(cams), f"{hits}/{len(cams)}")

    print("camera id inside the file name")
    ev = service.analyze(raw, f"cam{cams[0]}_{one.name}")
    check("camera read from the name", ev["type"] == "frame" and ev["cameraSource"] == "name" and ev["camera"] == cams[0])

    print("filed under the wrong camera")
    ev = service.analyze(raw, f"{cams[1]}/{one.name}")
    check("keeps the folder, warns about the mismatch", ev["type"] == "frame" and ev["camera"] == cams[1] and any("looks like camera" in w for w in ev["warnings"]), "; ".join(ev.get("warnings", [])))

    print("other sizes and formats")
    img = read_image(one)
    for label, im, ext in (("half size", cv2.resize(img, (640, 360)), ".jpg"), ("double size", cv2.resize(img, (2560, 1440)), ".jpg"),
                           ("png", img, ".png"), ("greyscale", cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), ".jpg"),
                           ("with alpha", cv2.cvtColor(img, cv2.COLOR_BGR2BGRA), ".png"), ("4:3 crop", img[:, 160:1120], ".jpg")):
        data = cv2.imencode(ext, im)[1].tobytes()
        ev = service.analyze(data, f"{cams[0]}/{one.stem}{ext}")
        check(label, ev["type"] == "frame" and complete(service, ev), "; ".join(ev.get("warnings", [])))

    print("unreadable image")
    ev = service.analyze(b"this is not a jpeg", f"{cams[0]}/1751099999.jpg")
    check("answered from memory, nothing missing", ev["type"] == "frame" and complete(service, ev) and all(v["source"] == "memory" for v in ev["frame"]["areas"].values()), "; ".join(ev.get("warnings", [])))
    ev = service.analyze(b"", "1751099998.jpg")
    check("no camera and no picture -> skipped with a reason", ev["type"] == "skip" and bool(ev["reason"]))

    print("odd names")
    ev = service.analyze(raw, f"{cams[0]}/photo final (2).jpg")
    check("file without a capture time", ev["type"] == "frame" and complete(service, ev) and ev["file"] == "photo final (2).jpg", "; ".join(ev.get("warnings", [])))
    ev = service.analyze(raw, "9999/1751052241.jpg")
    check("unknown camera folder falls back to the picture", ev["type"] == "frame" and ev["camera"] == cams[0] and ev["cameraSource"] == "auto")

    print("the organisers' rule for empty areas")
    answers = service.predictions("run")  # everything analysed so far, every camera
    seen_empty = [(c, i, a) for c, files in service.run.items() for i, record in files.items() for a, d in record["areas"].items() if d["stock_probs"][0] >= 0.5]
    check("an area seen as empty is reported planogram_compliant true", all(answers[c][i][a]["planogram_compliant"] is True for c, i, a in seen_empty), f"{len(seen_empty)} empty")

    print("zip with a wrapping folder and macOS debris")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for cam in cams[:3]:
            z.writestr(f"validation set/{cam}/{sample[cam].name}", sample[cam].read_bytes())
            z.writestr(f"__MACOSX/validation set/{cam}/._{sample[cam].name}", b"\x00\x05\x16\x07")
        z.writestr("validation set/readme.txt", "hello")
        z.writestr("validation set/.DS_Store", b"\x00")
    service.reset()
    events = list(service.analyze_items([("validation.zip", buf.getvalue())]))
    frames = [e for e in events if e["type"] == "frame"]
    check("three images analysed", len(frames) == 3 and all(complete(service, e) for e in frames))
    check("debris ignored, text file reported", [e["file"] for e in events if e["type"] == "skip"] == ["validation set/readme.txt"])
    check("summary event", events[-1]["type"] == "done" and events[-1]["images"] == 3)

    print("official export and scoring")
    pred = service.predictions("run")
    check("nested camera -> image -> area", all(set(v) == OFFICIAL for c in pred.values() for i in c.values() for v in i.values()))
    n = sum(len(i) for c in pred.values() for i in c.values())
    check("one entry per area", n == sum(len(service.areas[c]) for c in cams[:3]), str(n))
    res = service.score(json.loads(json.dumps(pred)))
    check("scoring its own output gives the maximum", res["score"] == res["max"] == 2 * n and not res["mistakes"], f"{res['score']}/{res['max']}")
    truth = json.loads(json.dumps(pred))
    cam0 = next(iter(truth))
    img0 = next(iter(truth[cam0]))
    truth[cam0][img0]["ghost_area"] = {"planogram_compliant": True, "stock_level": "full", "stock_value": 1.0}
    res = service.score(truth)
    check("an annotated area missing from the output costs 5", res["score"] == 2 * n - 5 and res["missing"] == 1, f"{res['score']}")

    service.reset()
    print(f"\n{'ALL GOOD' if not failures else 'FAILED: ' + ', '.join(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
