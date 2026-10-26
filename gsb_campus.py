"""
Stanford GSB (Knight Management Center) - low-poly block model, photo textured
Traced from GSB_KMC_Directory_Map_9_26.

Run in Blender: Scripting tab > Open this file > Run Script.
Re-running is safe: it clears and rebuilds only the "GSB_Campus" collection.

Textures come from make_textures.py and are expected in a "textures" folder
next to this script (or set TEXTURE_DIR). Missing textures fall back to flat
colors. In the viewport, set Solid shading > Color > Texture (or use Material
Preview) to see them.

Units: meters. +X = east, +Y = north (map top). Origin = Town Square.
Footprints are traced in map pixels (directory map PDF rendered at 100 dpi,
1400 x 850 px) and converted with PX_TO_M.
"""

import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

# ---------------------------------------------------------------- settings
PX_TO_M = 0.25            # meters per map pixel (rough estimate; tune later)
ORIGIN_PX = (595, 320)    # Town Square becomes world origin
STORY_H = 4.2             # meters per story
COLLECTION = "GSB_Campus"
TEXTURE_DIR = None        # None = "textures" folder next to this script
EXPORT_GLB = None         # e.g. "web/gsb_campus.glb" (relative to this script) for the Three.js viewer
EXPORT_IMAGE_FORMAT = "WEBP"  # textures inside the GLB: "WEBP" (smallest, keeps alpha), "JPEG", "AUTO" (PNG)
EXPORT_IMAGE_QUALITY = 75

# Stories per building. Bass, Arbuckle and Botha-Chan are read from the photos;
# the rest follow Botha-Chan (3 stories).
STORIES = {
    "Z_Zambrano_Hall": 3,
    "CM_Charlie_Munger": 3,
    "CM_Arbuckle_Neck": 1,
    "CM_Arbuckle_Pavilion": 2,
    "B_Bass_Center": 4,
    "BC_Botha_Chan_North": 3,
    "BC_Botha_Chan_West": 3,
    "BC_Botha_Chan_South": 3,
    "E_Faculty_East_North": 3,
    "E_Faculty_East_East": 3,
    "E_Faculty_East_South": 3,
    "G_Gunn_Building": 3,
    "M_McClelland_Building": 3,
    "C_MBA_Class_1968": 3,
    "P_Patterson_Building": 3,
}

# ---------------------------------------------------------------- architectural styles
# facade:      texture file in TEXTURE_DIR
# tex_w:       meters of wall one texture repeat covers (snapped so each
#              building's perimeter holds a whole number of repeats)
# tex_stories: stories one texture repeat covers vertically
# roof:        "hip" (red tile, with eave overhang) or "flat"
STYLES = {
    "botha_chan": dict(facade="botha_chan_facade.png", tex_w=13.0, tex_stories=3,
                       roof="hip", eave=0.9, roof_inset=2.2, roof_rise=1.3),
    "bass": dict(facade="bass_facade.png", tex_w=21.75, tex_stories=4,
                 roof="hip", eave=2.0, roof_inset=6.0, roof_rise=3.0),
    "arbuckle": dict(facade="arbuckle_facade.png", tex_w=14.0, tex_stories=2,
                     roof="flat", roof_mat="solar"),
    "plain": dict(facade="stucco.png", tex_w=4.0, tex_stories=1,
                  roof="flat", roof_mat="roof_flat"),
}
DEFAULT_STYLE = "botha_chan"
BUILDING_STYLE = {
    "B_Bass_Center": "bass",
    "CM_Arbuckle_Pavilion": "arbuckle",
    "CM_Arbuckle_Neck": "plain",
}
BRIDGE_STYLE = "plain"
ROOF_TILE_M = 3.0         # meters covered by one repeat of roof_tile.png

# ---------------------------------------------------------------- footprints (map pixels, x right / y down)
BUILDINGS = {
    "Z_Zambrano_Hall": [(235, 230), (235, 205), (252, 205), (252, 100), (278, 100),
                        (278, 85), (375, 85), (375, 118), (418, 150), (418, 230)],
    "CM_Charlie_Munger": [(418, 150), (458, 150), (458, 138), (488, 138), (488, 150),
                          (537, 150), (537, 245), (418, 245)],
    "CM_Arbuckle_Neck": [(445, 245), (492, 245), (492, 270), (445, 270)],
    "B_Bass_Center": [(568, 58), (655, 58), (655, 232), (568, 232)],
    "BC_Botha_Chan_North": [(692, 178), (710, 178), (710, 155), (788, 155), (788, 178),
                            (877, 178), (877, 232), (692, 232)],
    "BC_Botha_Chan_West": [(692, 232), (735, 232), (735, 325), (692, 325)],
    "BC_Botha_Chan_South": [(692, 325), (880, 325), (880, 382), (710, 382), (710, 355), (692, 345)],
    "E_Faculty_East_North": [(903, 178), (1100, 178), (1100, 232), (903, 232)],
    "E_Faculty_East_East": [(1100, 178), (1120, 178), (1120, 325), (1100, 325)],
    "E_Faculty_East_South": [(905, 325), (1120, 325), (1120, 382), (905, 382)],
    "G_Gunn_Building": [(163, 285), (255, 285), (255, 460), (163, 460)],
    "M_McClelland_Building": [(303, 478), (355, 478), (355, 460), (583, 460),
                              (583, 570), (303, 570)],
    "C_MBA_Class_1968": [(645, 460), (870, 460), (870, 570), (645, 570)],
    "P_Patterson_Building": [(903, 460), (1143, 460), (1143, 550), (1125, 550),
                             (1125, 570), (903, 570)],
}

# Circular pavilion: (center_px, radius_px)
ARBUCKLE = ((468, 318), 52)

# Elevated bridges between buildings: (name, footprint, start_story, stories)
BRIDGES = [
    ("Bridge_BC_E_North", [(877, 192), (903, 192), (903, 215), (877, 215)], 1, 1),
    ("Bridge_BC_E_South", [(880, 330), (905, 330), (905, 345), (880, 345)], 1, 1),
    ("Bridge_C_P", [(870, 466), (903, 466), (903, 478), (870, 478)], 1, 1),
]

# Neighboring buildings south of Jane Stanford Way (context massing, 2 stories)
CONTEXT = {
    "Jack_McDonald_Hall": [(320, 660), (583, 660), (583, 730), (320, 730)],
    "Investors_Common_Vidalakis": [(855, 660), (912, 660), (912, 680), (965, 680),
                                   (965, 800), (855, 800)],
    "Schwab_Residential_Center": [(965, 655), (1110, 655), (1110, 730), (965, 730)],
    "Context_SW_Block": [(113, 660), (300, 660), (300, 800), (113, 800)],
    "Context_S_Block": [(685, 665), (800, 665), (800, 800), (685, 800)],
    "Context_SE_Block": [(1120, 695), (1170, 695), (1170, 800), (1120, 800)],
}
CONTEXT_STORIES = 2

# Ground surfaces: (name, footprint, z_offset, material)
GROUND = [
    ("Ground_Base", [(0, 48), (1400, 48), (1400, 805), (0, 805)], 0.000, "ground"),
    ("King_Community_Court", [(270, 262), (407, 262), (407, 390), (270, 390)], 0.020, "grass"),
    ("Town_Square", [(540, 258), (648, 258), (648, 390), (540, 390)], 0.030, "plaza"),
    ("Town_Square_Walk", [(597, 390), (632, 390), (632, 588), (597, 588)], 0.030, "plaza"),
    ("McCoy_Family_Courtyard", [(735, 232), (1100, 232), (1100, 325), (735, 325)], 0.020, "plaza"),
    ("Knight_Way", [(255, 395), (1225, 395), (1225, 450), (255, 450)], 0.015, "path"),
    ("Jane_Stanford_Way", [(0, 588), (1400, 588), (1400, 620), (0, 620)], 0.010, "road"),
    ("Arguello_Way", [(88, 270), (105, 270), (105, 588), (88, 588)], 0.011, "road"),
    ("Campus_Drive_East", [(1110, 48), (1175, 48), (1260, 140), (1400, 300),
                           (1400, 375), (1200, 150)], 0.010, "road"),
]
GSB_BOWL = ((1262, 415), 42)

# Grass / paving mounds along Knight Way (half-ellipses bulging north):
# (name, x_left_px, x_right_px, base_y_px, top_y_px, material)
MOUNDS = [
    ("Mound_NGP", 282, 400, 448, 403, "grass"),
    ("Mound_Plaza_W", 427, 527, 448, 403, "plaza"),
    ("Mound_Walk_E", 543, 650, 448, 403, "grass"),
    ("Mound_TA_Cafe", 691, 791, 448, 403, "grass"),
    ("Mound_Plaza_E", 805, 927, 448, 403, "plaza"),
    ("Mound_E1", 945, 1055, 448, 403, "grass"),
    ("Mound_E2", 1064, 1200, 448, 403, "grass"),
]

# ---------------------------------------------------------------- Arbuckle pergola
# Dark steel grid canopy around the south and west of the pavilion. Cells whose
# center falls inside the drum are left out; beams run into the drum wall.
PERGOLA = {
    "rect_px": ((392, 285), (545, 392)),  # (north-west, south-east) corners
    "cell_m": 4.0,          # grid spacing
    "z": 4.0,               # underside of the beams (just below the drum's 2nd floor)
    "beam_w": 0.22,
    "beam_d": 0.45,
    "post_w": 0.18,
    "post_every": 2,        # a post at every Nth grid line
    "slat_m": 0.35,         # louver spacing inside each cell
}

# Metal cafe tables under the pergola, one per grid cell (at the cell center, so
# clear of the posts). Named Table_NN / Chair_NN_K; the web game seats people
# using those names.
FURNITURE = {
    "tables": 20,
    "chairs_per_table": 4,
    "drum_clear_m": 2.5,    # keep tables this far from the Arbuckle wall
    "chair_dist_m": 0.72,   # chair center to table center (before scaling)
    "scale": 1.5,           # furniture size vs real-world (seat 0.45 m -> 0.68 m)
    "seed": 11,
}

# ---------------------------------------------------------------- vegetation
# Rows of trees: (kind, start_px, end_px, count). Kinds are defined in TREE_KINDS.
TREE_ROWS = [
    ("broadleaf", (556, 272), (556, 380), 4),     # Town Square, west edge
    ("broadleaf", (634, 272), (634, 380), 4),     # Town Square, east edge
    ("broadleaf", (765, 250), (1075, 250), 6),    # McCoy Courtyard
    ("broadleaf", (765, 308), (1075, 308), 6),
    ("broadleaf", (128, 300), (128, 560), 4),     # between Arguello Way and Gunn
    ("conifer", (62, 290), (62, 560), 5),         # west of Arguello Way
    ("broadleaf", (120, 637), (1340, 637), 18),   # Jane Stanford Way street trees
    ("conifer", (850, 105), (1060, 105), 4),      # north of Botha-Chan / Faculty East
]
# Single trees: (kind, x_px, y_px)
TREES = [
    ("conifer", 245, 70), ("conifer", 305, 60), ("conifer", 345, 66),
    ("broadleaf", 405, 78), ("conifer", 445, 108),
    ("broadleaf", 1215, 470), ("broadleaf", 1300, 482), ("conifer", 1340, 430),
    ("broadleaf", 1250, 525), ("conifer", 1365, 520),
]
TREES_PER_MOUND = 2       # broadleaf trees on each grass mound
# Rows of shrubs: (start_px, end_px, count)
SHRUB_ROWS = [
    ((360, 454), (578, 454), 15),   # in front of McClelland
    ((650, 454), (865, 454), 15),   # in front of MBA Class of 1968
    ((908, 454), (1138, 454), 16),  # in front of Patterson
    ((272, 395), (405, 395), 9),    # south edge of King Community Court
]
SHRUBS_PER_MOUND = 3
VEG_SEED = 7              # change for a different random scatter

TREE_KINDS = {            # height range in meters
    "broadleaf": (7.0, 10.0),
    "conifer": (15.0, 22.0),
    "ornamental": (4.5, 6.0),
}

# ---------------------------------------------------------------- sky and sunlight
# The "sun" is a spot light placed far away in the sun's direction and aimed at
# Town Square: shadows fall like sunlight, but the light pool is an ellipse that
# fades to dark toward the outer buildings and the context blocks. Only the
# sky's dim ambient light reaches past it.
LIGHTING = {
    "target_px": (594, 324),     # Town Square center
    "elevation_deg": 55,         # sun height above the horizon
    "azimuth_deg": 200,          # compass direction of the sun (180 = due south)
    "distance_m": 600,           # how far away the spot sits (larger = more parallel shadows)
    "radius_ew_m": 160,          # light pool radius east-west (Gunn ~110 m, Patterson ~140 m)
    "radius_ns_m": 95,           # light pool radius north-south (context blocks start ~85 m south)
    "blend": 0.85,               # 0 = hard-edged pool, 1 = fades from the center outward
    "irradiance": 4.0,           # brightness at the center, in sun-strength units (W/m^2)
    "color": (1.0, 0.95, 0.86),  # warm sunlight
    "shadow_soft_m": 4.0,        # light radius; softens shadows
}
SKY = {
    "zenith": (0.02, 0.11, 0.55),
    "horizon": (0.30, 0.52, 0.88),
    "ground": (0.22, 0.36, 0.62),     # below the horizon (beyond the ground plane): hazy blue
    "view_strength": 1.0,        # brightness of the sky as seen by the camera
    "ambient_strength": 0.15,    # how much the sky lights the scene (low = darker edges)
}
HIDE_OTHER_LIGHTS = True  # hide (not delete) lights outside GSB_Campus, e.g. Blender's default Light

# ---------------------------------------------------------------- materials
# Flat colors; also the viewport color and the fallback when a texture is missing.
MATERIALS = {
    "botha_chan": (0.87, 0.74, 0.60, 1.0),  # warm stucco
    "bass":       (0.84, 0.68, 0.58, 1.0),
    "arbuckle":   (0.80, 0.72, 0.62, 1.0),
    "plain":      (0.87, 0.76, 0.63, 1.0),
    "roof_tile":  (0.60, 0.26, 0.20, 1.0),  # red clay tile
    "roof_flat":  (0.55, 0.53, 0.50, 1.0),
    "solar":      (0.16, 0.20, 0.30, 1.0),
    "context":    (0.75, 0.75, 0.75, 1.0),
    "ground":     (0.88, 0.87, 0.84, 1.0),
    "grass":      (0.62, 0.72, 0.40, 1.0),
    "plaza":      (0.93, 0.83, 0.62, 1.0),
    "path":       (0.82, 0.80, 0.74, 1.0),
    "road":       (0.45, 0.45, 0.47, 1.0),
    "steel":      (0.09, 0.09, 0.10, 1.0),  # pergola frame
    "iron":       (0.025, 0.025, 0.03, 1.0),  # cafe furniture frames (black wrought iron)
    "iron_mesh":  (0.03, 0.03, 0.035, 1.0),   # cafe table tops, seats and backs (perforated)
    "louver":     (0.12, 0.12, 0.13, 1.0),  # pergola slats (alpha-striped)
    "trunk":      (0.30, 0.22, 0.15, 1.0),
    "leaf_1":     (0.30, 0.45, 0.16, 1.0),
    "leaf_2":     (0.38, 0.52, 0.20, 1.0),
    "leaf_3":     (0.24, 0.38, 0.14, 1.0),
    "conifer":    (0.15, 0.28, 0.14, 1.0),
    "shrub":      (0.22, 0.36, 0.13, 1.0),
}
# (metallic, roughness) for materials that shouldn't use the default matte finish
MATERIAL_PBR = {"steel": (0.6, 0.45), "louver": (0.6, 0.45), "iron": (0.7, 0.45), "iron_mesh": (0.7, 0.5)}
TEXTURE_FILES = {key: s["facade"] for key, s in STYLES.items()}
TEXTURE_FILES["roof_tile"] = "roof_tile.png"


def script_dir():
    space = getattr(bpy.context, "space_data", None)
    text = getattr(space, "text", None)
    if text is not None and text.filepath:
        return os.path.dirname(bpy.path.abspath(text.filepath))
    path = globals().get("__file__")
    if path and os.path.isfile(path):
        return os.path.dirname(os.path.abspath(path))
    return bpy.path.abspath("//") or os.getcwd()


def texture_path(filename):
    folder = TEXTURE_DIR or os.path.join(script_dir(), "textures")
    path = os.path.join(bpy.path.abspath(folder), filename)
    return path if os.path.isfile(path) else None


_material_cache = {}


# See-through patterns cut with alpha, so a single quad reads as slats or wire mesh.
# Each is (size_px, opaque(row, col)); one UV unit = one repeat of the pattern.
ALPHA_PATTERNS = {
    "louver": (8, lambda row, col: row < 5),                 # ~60% slat, 40% gap
    "iron_mesh": (4, lambda row, col: row == 0 or col == 0),  # square wire grid, ~45% wire
}


def add_alpha_pattern(mat, bsdf, key):
    """Cut the material's alpha with ALPHA_PATTERNS[key].

    The pattern image is generated here and packed into the .blend, so there is no file
    to ship.
    """
    name = f"GSB_{key}_pattern"
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    size, opaque = ALPHA_PATTERNS[key]
    img = bpy.data.images.new(name, size, size, alpha=True)
    pixels = []
    for row in range(size):
        for col in range(size):
            pixels += [1.0, 1.0, 1.0, 1.0 if opaque(row, col) else 0.0]
    img.pixels = pixels
    img.pack()

    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Closest"
    tex.location = (bsdf.location.x - 320, bsdf.location.y - 300)
    links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    if hasattr(mat, "surface_render_method"):  # Blender 4.2+
        mat.surface_render_method = "DITHERED"
    else:
        mat.blend_method = "CLIP"


def get_material(key):
    """Material for key: image texture if available, else flat color. Rebuilt on each run."""
    if key in _material_cache:
        return _material_cache[key]
    name = f"GSB_{key}"
    old = bpy.data.materials.get(name)
    if old is not None:
        bpy.data.materials.remove(old)
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):  # node trees are always on from 5.0
        mat.use_nodes = True
    color = MATERIALS[key]
    mat.diffuse_color = color  # viewport solid-mode color
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    metallic, roughness = MATERIAL_PBR.get(key, (0.0, 0.85))
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Base Color"].default_value = color

    if key in ALPHA_PATTERNS:
        add_alpha_pattern(mat, bsdf, key)

    filename = TEXTURE_FILES.get(key)
    path = texture_path(filename) if filename else None
    if filename and path is None:
        print(f"GSB: texture {filename} not found, using flat color for {key}")
    if path:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(path, check_existing=True)
        tex.location = (bsdf.location.x - 320, bsdf.location.y)
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    _material_cache[key] = mat
    return mat


# ---------------------------------------------------------------- geometry helpers
def px(x, y):
    """Map pixel -> world meters (flip Y so north is +Y)."""
    return ((x - ORIGIN_PX[0]) * PX_TO_M, -(y - ORIGIN_PX[1]) * PX_TO_M)


def circle_pts(center, radius, segments=16):
    cx, cy = center
    return [(cx + radius * math.cos(2 * math.pi * i / segments),
             cy + radius * math.sin(2 * math.pi * i / segments)) for i in range(segments)]


def signed_area(pts):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))


def world_ccw(pts_px):
    """Footprint in world meters, counter-clockwise (so faces point up / walls out)."""
    pts = [px(*p) for p in pts_px]
    return pts if signed_area(pts) > 0 else pts[::-1]


def offset_polygon(pts, dist):
    """Offset a CCW polygon: dist > 0 grows it (eaves), dist < 0 shrinks it (roof inset).

    Returns None if the offset folds an edge back on itself (inset too deep for a wing).
    """
    n = len(pts)
    lines = []
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        dx, dy = dx / length, dy / length
        nx, ny = dy, -dx  # outward normal of a CCW polygon
        lines.append(((x1 + nx * dist, y1 + ny * dist), (dx, dy)))
    out = []
    for i in range(n):
        (p, d), (q, e) = lines[i - 1], lines[i]
        cross = d[0] * e[1] - d[1] * e[0]
        if abs(cross) < 1e-9:  # collinear edges
            out.append(q)
            continue
        t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / cross
        out.append((p[0] + d[0] * t, p[1] + d[1] * t))
    for i in range(n):  # every edge must keep its original direction
        (ax, ay), (bx, by) = out[i], out[(i + 1) % n]
        _, (dx, dy) = lines[i]
        if (bx - ax) * dx + (by - ay) * dy <= 0:
            return None
    return out if signed_area(out) > 0 else None


def new_object(name, bm, materials, collection, props=None):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for mat in materials:
        mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    for k, v in (props or {}).items():
        obj[k] = v
    return obj


def make_block(name, pts, height, z0, wall_mat, top_mat, collection,
               tex_w=4.0, tex_h=STORY_H, props=None):
    """Extrude a CCW world-space footprint into a closed block with wall UVs.

    Walls are UV-mapped by distance around the perimeter (u, wrapping cleanly
    because tex_w is snapped to a whole number of repeats) and height (v).
    Material slot 0 = walls, slot 1 = top and bottom.
    """
    n = len(pts)
    perim = [math.dist(pts[i], pts[(i + 1) % n]) for i in range(n)]
    total = sum(perim)
    tex_w = total / max(1, round(total / tex_w))

    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    bottom = [bm.verts.new((x, y, z0)) for x, y in pts]
    top = [bm.verts.new((x, y, z0 + height)) for x, y in pts]

    s = 0.0
    for i in range(n):
        j = (i + 1) % n
        face = bm.faces.new((bottom[i], bottom[j], top[j], top[i]))
        face.material_index = 0
        u0, u1 = s / tex_w, (s + perim[i]) / tex_w
        for loop, (u, v) in zip(face.loops, ((u0, 0), (u1, 0), (u1, height / tex_h), (u0, height / tex_h))):
            loop[uv].uv = (u, v)
        s += perim[i]

    for face in (bm.faces.new(top), bm.faces.new(bottom[::-1])):
        face.material_index = 1
        for loop in face.loops:
            loop[uv].uv = (loop.vert.co.x / tex_w, loop.vert.co.y / tex_w)

    return new_object(name, bm, [wall_mat, top_mat], collection, props)


def make_flat(name, pts, z, mat, collection):
    """Flat ground surface facing up."""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    face = bm.faces.new([bm.verts.new((x, y, z)) for x, y in pts])
    for loop in face.loops:
        loop[uv].uv = (loop.vert.co.x / 10, loop.vert.co.y / 10)
    return new_object(name, bm, [mat], collection)


def make_hip_roof(name, pts, z, eave, inset, rise, mat, collection):
    """Red-tile roof: eave overhang outside the walls, slopes up to an inset flat cap.

    If the inset is too deep for a narrow wing it is reduced (keeping the pitch).
    """
    outer = offset_polygon(pts, eave) or pts
    inner = None
    while inset > 0.3:
        inner = offset_polygon(pts, -inset)
        if inner:
            break
        rise *= 0.7
        inset *= 0.7
    if not inner:
        return None

    n = len(pts)
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    lo = [bm.verts.new((x, y, z)) for x, y in outer]
    hi = [bm.verts.new((x, y, z + rise)) for x, y in inner]

    for i in range(n):
        j = (i + 1) % n
        face = bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        # u along the eave, v up the slope, so tile rows run parallel to the eave
        ax, ay = outer[i]
        dx, dy = outer[j][0] - ax, outer[j][1] - ay
        length = math.hypot(dx, dy)
        dx, dy = dx / length, dy / length
        slope = math.hypot(eave + inset, rise) / (eave + inset)
        for loop in face.loops:
            rx, ry = loop.vert.co.x - ax, loop.vert.co.y - ay
            along = rx * dx + ry * dy
            across = -(rx * dy - ry * dx)  # inward horizontal distance
            loop[uv].uv = (along / ROOF_TILE_M, across * slope / ROOF_TILE_M)

    for face in (bm.faces.new(hi), bm.faces.new(lo[::-1])):  # cap, soffit
        for loop in face.loops:
            loop[uv].uv = (loop.vert.co.x / ROOF_TILE_M, loop.vert.co.y / ROOF_TILE_M)

    return new_object(name, bm, [mat], collection)


def make_building(name, pts_px, stories, style_key, collection, z0=0.0):
    style = STYLES[style_key]
    pts = world_ccw(pts_px)
    height = stories * STORY_H
    top_key = style.get("roof_mat", "roof_tile")
    make_block(name, pts, height, z0, get_material(style_key), get_material(top_key),
               collection, tex_w=style["tex_w"], tex_h=style["tex_stories"] * STORY_H,
               props={"stories": stories, "style": style_key})
    if style["roof"] == "hip":
        make_hip_roof(f"{name}_Roof", pts, z0 + height, style["eave"], style["roof_inset"],
                      style["roof_rise"], get_material("roof_tile"), collection)


def half_ellipse_pts(x0, x1, base_y, top_y, segments=14):
    """Half-ellipse in map px with its flat side on base_y, bulging toward top_y."""
    cx, a, b = (x0 + x1) / 2, (x1 - x0) / 2, base_y - top_y
    return [(cx - a * math.cos(math.pi * i / segments), base_y - b * math.sin(math.pi * i / segments))
            for i in range(segments + 1)]


def add_box(bm, center, size):
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.LocRotScale(center, None, size))


# ---------------------------------------------------------------- Arbuckle pergola
def pergola_grid():
    """The pergola's grid: (nx, ny, cell_w, cell_h, gx, gy, drum_dist).

    gx(i) / gy(j) give world x / y of grid line i / j; drum_dist(x, y) is the distance
    from the Arbuckle drum wall (negative inside the drum).
    """
    p = PERGOLA
    (ax, ay), (bx, by) = p["rect_px"]
    x0, y1 = px(ax, ay)  # north-west corner (world y is up)
    x1, y0 = px(bx, by)
    nx = max(1, round((x1 - x0) / p["cell_m"]))
    ny = max(1, round((y1 - y0) / p["cell_m"]))
    cw, ch = (x1 - x0) / nx, (y1 - y0) / ny
    (dcx, dcy), dr = px(*ARBUCKLE[0]), ARBUCKLE[1] * PX_TO_M
    return (nx, ny, cw, ch, lambda i: x0 + i * cw, lambda j: y0 + j * ch,
            lambda x, y: math.hypot(x - dcx, y - dcy) - dr)


def make_pergola(collection):
    p = PERGOLA
    nx, ny, cw, ch, gx, gy, drum_dist = pergola_grid()

    def in_drum(x, y):
        return drum_dist(x, y) < 0

    cells = [(i, j) for i in range(nx) for j in range(ny)
             if not in_drum(gx(i + 0.5), gy(j + 0.5))]
    if not cells:
        return

    z_beam = p["z"] + p["beam_d"] / 2
    edges = set()
    for i, j in cells:
        edges.update({("x", i, j), ("x", i, j + 1), ("y", i, j), ("y", i + 1, j)})

    frame = bmesh.new()
    for axis, i, j in edges:
        if axis == "x":  # beam along x from grid point (i, j) to (i+1, j)
            add_box(frame, (gx(i + 0.5), gy(j), z_beam), (cw + p["beam_w"], p["beam_w"], p["beam_d"]))
        else:
            add_box(frame, (gx(i), gy(j + 0.5), z_beam), (p["beam_w"], ch + p["beam_w"], p["beam_d"]))

    corners = {(i + di, j + dj) for i, j in cells for di in (0, 1) for dj in (0, 1)}
    k = p["post_every"]
    for i, j in corners:
        on_edge = i in (0, nx) or j in (0, ny)
        if (i % k == 0 and j % k == 0) or (on_edge and (i + j) % k == 0):
            if not in_drum(gx(i), gy(j)):
                add_box(frame, (gx(i), gy(j), p["z"] / 2), (p["post_w"], p["post_w"], p["z"]))
    new_object("Arbuckle_Pergola_Frame", frame, [get_material("steel")], collection)

    # One louvered quad per cell, at mid-beam height; v counts slats.
    louvers = bmesh.new()
    uv = louvers.loops.layers.uv.new("UVMap")
    for i, j in cells:
        quad = [(gx(i), gy(j)), (gx(i + 1), gy(j)), (gx(i + 1), gy(j + 1)), (gx(i), gy(j + 1))]
        face = louvers.faces.new([louvers.verts.new((x, y, z_beam)) for x, y in quad])
        for loop in face.loops:
            loop[uv].uv = ((loop.vert.co.x - gx(i)) / cw, (loop.vert.co.y - gy(j)) / p["slat_m"])
    new_object("Arbuckle_Pergola_Louvers", louvers, [get_material("louver")], collection)


# Wrought-iron patio set: black tube frames (slot 0, "iron") with perforated mesh
# tops, seats and backs (slot 1, "iron_mesh", alpha-cut wire grid). Modeled at
# real-world size, then scaled by FURNITURE["scale"].
MESH_CELL_M = 0.04  # wire-grid spacing before scaling
TUBE_M = 0.024      # frame tube thickness before scaling


def add_strut(bm, p0, p1, t=TUBE_M):
    """Square tube from p0 to p1."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    q = Vector((0, 0, 1)).rotation_difference(d.normalized())
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.LocRotScale((p0 + p1) / 2, q, (t, t, d.length)))


def add_mesh_panel(bm, uv, corners):
    """Perforated panel through the given corners (material slot 1), wire grid in UVs."""
    pts = [Vector(c) for c in corners]
    face = bm.faces.new([bm.verts.new(p) for p in pts])
    face.material_index = 1
    e1 = (pts[1] - pts[0]).normalized()
    e2 = (pts[-1] - pts[0])
    e2 = (e2 - e1 * e2.dot(e1)).normalized()
    for loop in face.loops:
        r = loop.vert.co - pts[0]
        loop[uv].uv = (r.dot(e1) / MESH_CELL_M, r.dot(e2) / MESH_CELL_M)


def finish_furniture_mesh(bm, name):
    s = FURNITURE["scale"]
    bmesh.ops.scale(bm, vec=(s, s, s), verts=bm.verts)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(get_material("iron"))
    mesh.materials.append(get_material("iron_mesh"))
    return mesh


def build_table_mesh():
    """Round mesh-top patio table: 0.92 m across, 0.74 m high, four splayed legs."""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    top_z, n = 0.74, 20
    add_mesh_panel(bm, uv, [(0.45 * math.cos(2 * math.pi * i / n), 0.45 * math.sin(2 * math.pi * i / n), top_z)
                            for i in range(n)])
    bmesh.ops.create_cone(bm, cap_ends=False, segments=n, radius1=0.46, radius2=0.46, depth=0.035,
                          matrix=Matrix.Translation((0, 0, top_z - 0.012)))  # rim
    bmesh.ops.create_cone(bm, cap_ends=False, segments=10, radius1=0.1, radius2=0.1, depth=0.03,
                          matrix=Matrix.Translation((0, 0, 0.42)))           # center ring
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        c, s = math.cos(a), math.sin(a)
        rim, knee, foot = (0.40 * c, 0.40 * s, top_z - 0.02), (0.30 * c, 0.30 * s, 0.42), (0.41 * c, 0.41 * s, 0.0)
        add_strut(bm, rim, knee)
        add_strut(bm, knee, foot)
        add_strut(bm, (0.1 * c, 0.1 * s, 0.42), knee, TUBE_M * 0.8)  # spoke to the ring
    return finish_furniture_mesh(bm, "GSB_Table")


def build_chair_mesh():
    """Mesh armchair facing local +Y: seat at 0.45 m, tall back reclined toward -Y."""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    w, fy, by, seat = 0.23, 0.21, -0.21, 0.45   # half width, front / back seat edge, seat height
    top_y, top_z, top_w = -0.33, 1.0, 0.25       # top of the reclined back
    for sx in (-1, 1):
        add_strut(bm, (sx * w, fy, 0), (sx * w, fy, seat))               # front leg
        add_strut(bm, (sx * w, by - 0.03, 0), (sx * w, by, seat))        # back leg
        add_strut(bm, (sx * w, by, seat), (sx * top_w, top_y, top_z))    # back upright
        add_strut(bm, (sx * w, by, seat), (sx * w, fy, seat))            # seat side rail
        arm_back = (sx * 0.238, -0.26, 0.68)
        add_strut(bm, arm_back, (sx * 0.25, 0.13, 0.68))                 # armrest
        add_strut(bm, (sx * 0.25, 0.13, 0.68), (sx * 0.24, fy, 0.58))    # armrest curving down
        add_strut(bm, (sx * 0.24, fy, 0.58), (sx * w, fy, seat))
    add_strut(bm, (-w, fy, seat), (w, fy, seat))                         # front rail
    add_strut(bm, (-w, by, seat), (w, by, seat))                         # back rail
    add_strut(bm, (-top_w, top_y, top_z), (top_w, top_y, top_z))        # top of the back
    add_mesh_panel(bm, uv, [(-w, by, seat), (w, by, seat), (w, fy, seat), (-w, fy, seat)])
    add_mesh_panel(bm, uv, [(w, by, seat + 0.02), (-w, by, seat + 0.02),
                            (-top_w, top_y, top_z - 0.02), (top_w, top_y, top_z - 0.02)])
    return finish_furniture_mesh(bm, "GSB_Chair")


def make_furniture(collection):
    f = FURNITURE
    nx, ny, cw, ch, gx, gy, drum_dist = pergola_grid()
    spots = [(gx(i + 0.5), gy(j + 0.5)) for i in range(nx) for j in range(ny)
             if drum_dist(gx(i + 0.5), gy(j + 0.5)) > f["drum_clear_m"]]
    rng = random.Random(f["seed"])
    rng.shuffle(spots)
    spots = sorted(spots[:f["tables"]], key=lambda s: (-s[1], s[0]))  # number them north to south
    if len(spots) < f["tables"]:
        print(f"GSB: only room for {len(spots)} tables under the pergola")

    table_mesh, chair_mesh = build_table_mesh(), build_chair_mesh()
    n = f["chairs_per_table"]
    for t, (x, y) in enumerate(spots):
        table = bpy.data.objects.new(f"Table_{t:02d}", table_mesh)
        table.location = (x, y, 0.0)
        collection.objects.link(table)
        turn = rng.uniform(0, 2 * math.pi / n)
        for k in range(n):
            theta = turn + 2 * math.pi * k / n
            chair = bpy.data.objects.new(f"Chair_{t:02d}_{k}", chair_mesh)
            d = f["chair_dist_m"] * f["scale"]
            chair.location = (x + d * math.cos(theta), y + d * math.sin(theta), 0.0)
            chair.rotation_euler = (0, 0, theta + math.pi / 2)  # local +Y faces the table
            collection.objects.link(chair)


# ---------------------------------------------------------------- vegetation
def build_tree_meshes():
    """One shared low-poly mesh per tree kind, 1 m tall (objects scale it up).

    Slot 0 = trunk, slot 1 = foliage (set per object so leaf colors can vary).
    """
    meshes = {}
    for kind in TREE_KINDS:
        bm = bmesh.new()
        trunk_h = 0.25 if kind == "conifer" else 0.45
        bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.035, radius2=0.03,
                              depth=trunk_h, matrix=Matrix.Translation((0, 0, trunk_h / 2)))
        trunk_faces = set(bm.faces)
        if kind == "conifer":
            bmesh.ops.create_cone(bm, cap_ends=True, segments=7, radius1=0.2, radius2=0.0,
                                  depth=0.85, matrix=Matrix.Translation((0, 0, 0.575)))
        else:
            r = 0.33 if kind == "ornamental" else 0.3
            bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r,
                                       matrix=Matrix.LocRotScale((0, 0, 0.62), None, (1, 1, 0.85)))
        for f in bm.faces:
            f.material_index = 0 if f in trunk_faces else 1
        mesh = bpy.data.meshes.new(f"GSB_Tree_{kind}")
        bm.to_mesh(mesh)
        bm.free()
        mesh.materials.append(get_material("trunk"))
        mesh.materials.append(get_material("leaf_1"))
        meshes[kind] = mesh
    return meshes


def build_shrub_mesh():
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.5,
                               matrix=Matrix.LocRotScale((0, 0, 0.35), None, (1, 1, 0.75)))
    mesh = bpy.data.meshes.new("GSB_Shrub")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(get_material("shrub"))
    return mesh


def point_in_poly(x, y, poly):
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def blocked(x, y, margin_px):
    """True if a plant at map px (x, y) would sit in a building or under the pergola."""
    for poly in list(BUILDINGS.values()) + list(CONTEXT.values()):
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        if min(xs) - margin_px < x < max(xs) + margin_px and min(ys) - margin_px < y < max(ys) + margin_px:
            if point_in_poly(x, y, poly) or any(
                    point_in_poly(x + dx, y + dy, poly)
                    for dx, dy in ((margin_px, 0), (-margin_px, 0), (0, margin_px), (0, -margin_px))):
                return True
    (cx, cy), r = ARBUCKLE
    if math.hypot(x - cx, y - cy) < r + margin_px:
        return True
    (ax, ay), (bx, by) = PERGOLA["rect_px"]
    return ax < x < bx and ay < y < by


def vegetation_points(rng):
    """Expand TREE_ROWS / TREES / mounds into (kind, x_px, y_px) with a little jitter."""
    pts = list(TREES)
    for kind, (x0, y0), (x1, y1), n in TREE_ROWS:
        for k in range(n):
            t = k / (n - 1) if n > 1 else 0.5
            pts.append((kind, x0 + (x1 - x0) * t + rng.uniform(-3, 3), y0 + (y1 - y0) * t + rng.uniform(-3, 3)))
    for _, x0, x1, base, top, mat in MOUNDS:
        if mat == "grass":
            for k in range(TREES_PER_MOUND):
                t = (k + 1) / (TREES_PER_MOUND + 1)
                pts.append(("broadleaf", x0 + (x1 - x0) * t, (base + top) / 2 + rng.uniform(-4, 4)))
    return pts


def make_vegetation(collection):
    rng = random.Random(VEG_SEED)
    tree_meshes = build_tree_meshes()
    leaf_mats = [get_material(k) for k in ("leaf_1", "leaf_2", "leaf_3")]
    conifer_mat = get_material("conifer")

    count = 0
    for kind, x, y in vegetation_points(rng):
        lo, hi = TREE_KINDS[kind]
        h = rng.uniform(lo, hi)
        canopy_px = h * 0.3 / PX_TO_M
        if blocked(x, y, canopy_px):
            continue
        obj = bpy.data.objects.new(f"Tree_{kind}_{count:03d}", tree_meshes[kind])
        wx, wy = px(x, y)
        obj.location = (wx, wy, 0.0)
        obj.rotation_euler = (0, 0, rng.uniform(0, 2 * math.pi))
        s = rng.uniform(0.85, 1.15)
        obj.scale = (h * s, h * s, h)
        collection.objects.link(obj)
        obj.material_slots[1].link = "OBJECT"
        obj.material_slots[1].material = conifer_mat if kind == "conifer" else rng.choice(leaf_mats)
        count += 1

    shrub_mesh = build_shrub_mesh()
    shrubs = []
    for (x0, y0), (x1, y1), n in SHRUB_ROWS:
        for k in range(n):
            t = k / (n - 1) if n > 1 else 0.5
            shrubs.append((x0 + (x1 - x0) * t + rng.uniform(-2, 2), y0 + (y1 - y0) * t + rng.uniform(-1, 1)))
    for _, x0, x1, base, top, mat in MOUNDS:
        if mat == "grass":
            for _ in range(SHRUBS_PER_MOUND):
                shrubs.append((rng.uniform(x0 + 15, x1 - 15), rng.uniform(top + 12, base - 4)))
    placed = 0
    for x, y in shrubs:
        if blocked(x, y, 1):
            continue
        obj = bpy.data.objects.new(f"Shrub_{placed:03d}", shrub_mesh)
        placed += 1
        wx, wy = px(x, y)
        w = rng.uniform(1.1, 1.8)
        obj.location = (wx, wy, 0.0)
        obj.rotation_euler = (0, 0, rng.uniform(0, 2 * math.pi))
        obj.scale = (w, w * rng.uniform(0.8, 1.2), rng.uniform(0.8, 1.2))
        collection.objects.link(obj)
    print(f"GSB vegetation: {count} trees, {placed} shrubs")


# ---------------------------------------------------------------- sky and sunlight
def make_sunlight(collection):
    """Spot light in the sun's direction, aimed at Town Square, with an elliptical pool."""
    L = LIGHTING
    tx, ty = px(*L["target_px"])
    e, a, d = math.radians(L["elevation_deg"]), math.radians(L["azimuth_deg"]), L["distance_m"]
    to_sun = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))

    light = bpy.data.lights.new("GSB_Sun", type="SPOT")
    # Ground radius r at distance d needs a half-angle atan(r / d). The local Y axis
    # lies in the sun's vertical plane, where the pool stretches by 1 / sin(elevation),
    # so squash Y by sin(elevation) and the N-S / E-W ratio.
    light.spot_size = 2 * math.atan(L["radius_ew_m"] / d)
    light.spot_blend = L["blend"]
    light.energy = L["irradiance"] * 4 * math.pi * d * d  # point-light watts giving that irradiance at d
    light.color = L["color"]
    light.shadow_soft_size = L["shadow_soft_m"]
    if hasattr(light, "show_cone"):
        light.show_cone = True

    obj = bpy.data.objects.new("GSB_Sun", light)
    obj.location = Vector((tx, ty, 0.0)) + to_sun * d
    obj.rotation_euler = (-to_sun).to_track_quat("-Z", "Y").to_euler()
    obj.scale = (1.0, math.sin(e) * L["radius_ns_m"] / L["radius_ew_m"], 1.0)
    collection.objects.link(obj)

    if HIDE_OTHER_LIGHTS:
        ours = set(collection.all_objects)
        for other in bpy.data.objects:
            if other.type == "LIGHT" and other not in ours:
                other.hide_render = True
                other.hide_viewport = True
                print(f"GSB: hid light '{other.name}' (set HIDE_OTHER_LIGHTS = False to keep it)")


def make_sky():
    """Blue gradient sky. The camera sees it at full strength; it lights the scene dimly."""
    name = "GSB_Sky"
    old = bpy.data.worlds.get(name)
    if old is not None:
        bpy.data.worlds.remove(old)
    world = bpy.data.worlds.new(name)
    if bpy.app.version < (5, 0, 0):
        world.use_nodes = True
    world.color = SKY["horizon"]
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()

    coord = nodes.new("ShaderNodeTexCoord")
    xyz = nodes.new("ShaderNodeSeparateXYZ")
    ramp = nodes.new("ShaderNodeValToRGB")  # view direction height -> sky color
    ramp.color_ramp.elements[0].position = 0.47
    ramp.color_ramp.elements[0].color = (*SKY["ground"], 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (*SKY["zenith"], 1.0)
    horizon = ramp.color_ramp.elements.new(0.5)
    horizon.color = (*SKY["horizon"], 1.0)
    to_unit = nodes.new("ShaderNodeMapRange")  # z in [-1, 1] -> [0, 1]
    to_unit.inputs["From Min"].default_value = -1.0

    path = nodes.new("ShaderNodeLightPath")
    strength = nodes.new("ShaderNodeMath")  # is_camera * (view - ambient) + ambient
    strength.operation = "MULTIPLY_ADD"
    strength.inputs[1].default_value = SKY["view_strength"] - SKY["ambient_strength"]
    strength.inputs[2].default_value = SKY["ambient_strength"]

    bg = nodes.new("ShaderNodeBackground")
    out = nodes.new("ShaderNodeOutputWorld")
    links.new(coord.outputs["Generated"], xyz.inputs["Vector"])
    links.new(xyz.outputs["Z"], to_unit.inputs["Value"])
    links.new(to_unit.outputs["Result"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bg.inputs["Color"])
    links.new(path.outputs["Is Camera Ray"], strength.inputs[0])
    links.new(strength.outputs["Value"], bg.inputs["Strength"])
    links.new(bg.outputs["Background"], out.inputs["Surface"])
    for i, node in enumerate((coord, xyz, to_unit, ramp, path, strength, bg, out)):
        node.location = (i * 220 - 800, 0)

    bpy.context.scene.world = world


# ---------------------------------------------------------------- scene management
def reset_collection(name):
    root = bpy.data.collections.get(name)
    if root:
        for col in [root] + list(root.children_recursive):
            for obj in list(col.objects):
                data = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if data is not None and data.users == 0:
                    if isinstance(data, bpy.types.Mesh):
                        bpy.data.meshes.remove(data)
                    elif isinstance(data, bpy.types.Light):
                        bpy.data.lights.remove(data)
        for child in list(root.children_recursive):
            bpy.data.collections.remove(child)
        for mesh in list(bpy.data.meshes):  # shared tree/shrub meshes left without objects
            if mesh.users == 0 and mesh.name.startswith("GSB_"):
                bpy.data.meshes.remove(mesh)
    else:
        root = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(root)
    return root


def sub_collection(parent, name):
    col = bpy.data.collections.new(name)
    parent.children.link(col)
    return col


# ---------------------------------------------------------------- build
def build():
    _material_cache.clear()
    root = reset_collection(COLLECTION)
    c_bld = sub_collection(root, "GSB_Buildings")
    c_ctx = sub_collection(root, "GSB_Context")
    c_gnd = sub_collection(root, "GSB_Ground")
    c_veg = sub_collection(root, "GSB_Vegetation")

    for name, pts in BUILDINGS.items():
        make_building(name, pts, STORIES[name], BUILDING_STYLE.get(name, DEFAULT_STYLE), c_bld)

    make_building("CM_Arbuckle_Pavilion", circle_pts(*ARBUCKLE), STORIES["CM_Arbuckle_Pavilion"],
                  BUILDING_STYLE.get("CM_Arbuckle_Pavilion", DEFAULT_STYLE), c_bld)

    for name, pts, start, n in BRIDGES:
        make_building(name, pts, n, BRIDGE_STYLE, c_bld, z0=start * STORY_H)

    for name, pts in CONTEXT.items():
        make_block(name, world_ccw(pts), CONTEXT_STORIES * STORY_H, 0.0, get_material("context"),
                   get_material("context"), c_ctx, props={"stories": CONTEXT_STORIES})

    for name, pts, z, mat in GROUND:
        make_flat(name, world_ccw(pts), z, get_material(mat), c_gnd)
    make_flat("GSB_Bowl", world_ccw(circle_pts(*GSB_BOWL, segments=20)), 0.025,
              get_material("grass"), c_gnd)
    for name, x0, x1, base, top, mat in MOUNDS:
        make_flat(name, world_ccw(half_ellipse_pts(x0, x1, base, top)), 0.022, get_material(mat), c_gnd)

    make_pergola(c_bld)
    make_furniture(sub_collection(root, "GSB_Furniture"))
    make_vegetation(c_veg)

    make_sunlight(root)
    make_sky()

    if EXPORT_GLB:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in root.all_objects:
            if obj.type == "MESH":
                obj.select_set(True)
        path = bpy.path.abspath(EXPORT_GLB) if EXPORT_GLB.startswith("//") else EXPORT_GLB
        if not os.path.isabs(path):
            path = os.path.join(script_dir(), path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=path,
                                  use_selection=True, export_format="GLB",
                                  export_image_format=EXPORT_IMAGE_FORMAT,
                                  export_image_quality=EXPORT_IMAGE_QUALITY,
                                  export_jpeg_quality=EXPORT_IMAGE_QUALITY)

    faces = sum(len(o.data.polygons) for o in root.all_objects if o.type == "MESH")
    print(f"GSB campus built: {len(root.all_objects)} objects, {faces} faces")


build()
