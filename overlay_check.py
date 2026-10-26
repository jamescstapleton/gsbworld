"""
Draw the footprints from gsb_campus.py on top of the directory-map PDF so you
can see how well the traced coordinates line up.

Usage:
    pip install pymupdf
    python overlay_check.py gsb_campus.py "GSB_KMC_Directory_Map_9_26 Color Icons.pdf" overlay.png

The Blender script's pixel coordinates correspond to the PDF rendered at
100 dpi (1400 x 850 px). The data dicts are read with `ast`, so Blender/bpy
is not needed.
"""

import ast
import math
import sys

import fitz  # PyMuPDF

DPI = 100
PT_PER_PX = 72 / DPI

COLORS = {
    "BUILDINGS": (0.85, 0.0, 0.0),
    "BRIDGES": (0.6, 0.0, 0.8),
    "CONTEXT": (0.0, 0.35, 0.9),
    "GROUND": (0.0, 0.6, 0.2),
}


def load_data(script_path):
    tree = ast.parse(open(script_path, encoding="utf-8").read())
    data = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                data[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return data


def circle_pts(center, radius, segments=24):
    cx, cy = center
    return [(cx + radius * math.cos(2 * math.pi * i / segments),
             cy + radius * math.sin(2 * math.pi * i / segments)) for i in range(segments)]


def shapes(data):
    for name, pts in data.get("BUILDINGS", {}).items():
        yield "BUILDINGS", name, pts
    if "ARBUCKLE" in data:
        yield "BUILDINGS", "CM_Arbuckle_Pavilion", circle_pts(*data["ARBUCKLE"])
    for name, pts, *_ in data.get("BRIDGES", []):
        yield "BRIDGES", name, pts
    for name, pts in data.get("CONTEXT", {}).items():
        yield "CONTEXT", name, pts
    for name, pts, *_ in data.get("GROUND", []):
        if name != "Ground_Base":
            yield "GROUND", name, pts
    if "GSB_BOWL" in data:
        yield "GROUND", "GSB_Bowl", circle_pts(*data["GSB_BOWL"])


def main(script_path, pdf_path, out_path):
    data = load_data(script_path)
    doc = fitz.open(pdf_path)
    page = doc[0]
    for group, name, pts in shapes(data):
        color = COLORS[group]
        poly = [fitz.Point(x * PT_PER_PX, y * PT_PER_PX) for x, y in pts]
        shape = page.new_shape()
        shape.draw_polyline(poly + poly[:1])
        shape.finish(color=color, width=1.2, dashes="[3 2]" if group == "GROUND" else None)
        shape.commit()
        cx = sum(p.x for p in poly) / len(poly)
        cy = sum(p.y for p in poly) / len(poly)
        page.insert_text((cx - 20, cy), name, fontsize=4.5, color=color)
    page.get_pixmap(dpi=int(DPI * 1.5)).save(out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
