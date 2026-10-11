"""How many answers changed between two predictions.json files (e.g. before and after a speed-up)?

usage: python tools/compare_predictions.py <before.json> <after.json>

Prints how many (image, area) answers agree on stock level and on compliance, and lists the
ones that changed. A speed-up that keeps the quality should change none, or only a handful
of borderline areas.
"""
import json
import sys


def flat(path):
    d = json.load(open(path, encoding="utf-8"))
    out = {}
    for cam, images in d.items():
        for img, areas in images.items():
            for area, v in areas.items():
                out[(cam, img, area)] = v
    return out


def main():
    a, b = flat(sys.argv[1]), flat(sys.argv[2])
    keys = sorted(set(a) & set(b))
    only = len(set(a) ^ set(b))
    stock = [k for k in keys if a[k].get("stock_level") != b[k].get("stock_level")]
    comp = [k for k in keys if a[k].get("planogram_compliant") != b[k].get("planogram_compliant")]
    n = len(keys)
    print(f"{n} answers in both files{f', {only} in only one of them' if only else ''}")
    print(f"stock level: {n - len(stock)} / {n} the same ({100 * (n - len(stock)) / max(n, 1):.2f}%)")
    print(f"compliance:  {n - len(comp)} / {n} the same ({100 * (n - len(comp)) / max(n, 1):.2f}%)")
    for k in stock[:40]:
        print(f"  stock {k[2]:8s} {k[1]}: {a[k].get('stock_level')} -> {b[k].get('stock_level')}")
    for k in comp[:40]:
        print(f"  comply {k[2]:8s} {k[1]}: {a[k].get('planogram_compliant')} -> {b[k].get('planogram_compliant')}")


if __name__ == "__main__":
    main()
