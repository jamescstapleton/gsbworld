"""
Cut flat, rectified facade textures out of the GSB reference photos.

Usage:
    pip install pillow
    python make_textures.py <photo_dir> <out_dir>

<photo_dir> must contain bass.png and arbuckle.jpg (the files from the
GSB World folder). Writes into <out_dir>:

    bass_facade.png        Bass Center south face, 3 bays x 4 stories
    botha_chan_facade.png  Botha-Chan style wall, 3 stories (default style)
    arbuckle_facade.png    Arbuckle Pavilion drum, 2 stories
    roof_tile.png          red clay tile, tileable
    stucco.png             plain stucco, tileable

Quads are (top-left, top-right, bottom-right, bottom-left) in photo pixels,
picked by hand from the photos. Nudge them if a texture looks skewed.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFilter

# ---------------------------------------------------------------- source quads (photo px)
BASS_FRONT = [(168, 94), (1100, 214), (1100, 930), (168, 969)]   # bass.png
BC_UPPER = [(1300, 455), (1770, 452), (1770, 758), (1300, 762)]  # bass.png, floors 2-3
ARB_UPPER = [(455, 57), (670, 57), (670, 150), (455, 150)]       # arbuckle.jpg, parapet + glass
ARB_GLASS = [(455, 100), (670, 100), (670, 150), (455, 150)]     # arbuckle.jpg, glass band only
ROOF = [(330, 30), (880, 92), (880, 128), (330, 64)]             # bass.png, roof slope
STUCCO = [(1320, 702), (1540, 702), (1540, 740), (1320, 740)]    # bass.png, plain wall band
STUCCO_SAMPLE = (1320, 702, 1540, 740)                           # same band, as a crop box

FLOOR_PX = 256  # output pixels per story

# Bass ground floor redraw, in rectified-texture px (1200 x 1024)
BASS_LINTEL_Y = 765
BASS_PIERS = [(0, 107), (250, 285), (445, 505), (630, 665), (818, 875), (990, 1025), (1144, 1200)]


def rectify(img, quad, size):
    """Warp a quadrilateral region of img into a size=(w, h) rectangle."""
    tl, tr, br, bl = quad
    data = (*tl, *bl, *br, *tr)  # PIL QUAD order: UL, LL, LR, UR
    return img.transform(size, Image.QUAD, data, resample=Image.BICUBIC)


def make_tileable(tex, blend_px=24):
    """Cross-fade the right edge into the left so the texture repeats without a hard seam.

    The result is blend_px narrower: its last column is followed (on wrap) by a
    first column that starts as the old right-edge strip and fades into the left.
    """
    w, h = tex.size
    right = tex.crop((w - blend_px, 0, w, h))
    left = tex.crop((0, 0, blend_px, h))
    ramp = Image.new("L", (blend_px, 1))
    ramp.putdata([int(255 * x / (blend_px - 1)) for x in range(blend_px)])
    mask = ramp.resize((blend_px, h))  # 0 at x=0 (right strip) -> 255 (left strip)
    out = tex.crop((0, 0, w - blend_px, h))
    out.paste(Image.composite(left, right, mask), (0, 0))
    return out


def avg_color(img, box):
    return img.crop(box).resize((1, 1), Image.BOX).getpixel((0, 0))


def arcade_band(width, height, stucco, shadow, bays):
    """Procedural ground-floor arcade: stucco piers with shaded openings."""
    band = Image.new("RGB", (width, height), stucco)
    d = ImageDraw.Draw(band)
    bay_w = width / bays
    pier = bay_w * 0.22
    for i in range(bays):
        x0 = i * bay_w + pier / 2
        d.rectangle([x0, height * 0.14, x0 + bay_w - pier, height], fill=shadow)
    d.rectangle([0, 0, width, height * 0.06], fill=tuple(int(c * 0.9) for c in stucco))  # floor band
    return band.filter(ImageFilter.GaussianBlur(0.8))


def main(photo_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    bass = Image.open(os.path.join(photo_dir, "bass.png")).convert("RGB")
    arb = Image.open(os.path.join(photo_dir, "arbuckle.jpg")).convert("RGB")

    stucco = avg_color(bass, STUCCO_SAMPLE)  # sunlit wall, shared by all the stucco buildings

    # Bass: 3 bays x 4 stories. Trees, lamps and people cover the ground floor,
    # so redraw it below the lintel: stucco piers under the upper piers, dark glazing between.
    w, h = 3 * 400, 4 * FLOOR_PX
    tex = rectify(bass, BASS_FRONT, (w, h))
    glass = avg_color(tex, (150, 400, 250, 700))
    d = ImageDraw.Draw(tex)
    d.rectangle([0, BASS_LINTEL_Y, w, h], fill=glass)
    d.rectangle([0, BASS_LINTEL_Y, w, BASS_LINTEL_Y + 50], fill=tuple(int(c * 0.9) for c in stucco))
    for x0, x1 in BASS_PIERS:
        d.rectangle([x0, BASS_LINTEL_Y + 50, x1, h], fill=stucco)
    tex.save(os.path.join(out_dir, "bass_facade.png"))

    # Botha-Chan: photo gives floors 2-3; ground floor (hidden by trees) is a
    # procedural arcade using colors sampled from the photo.
    upper = rectify(bass, BC_UPPER, (800, 2 * FLOOR_PX))
    shadow = tuple(int(c * 0.4) for c in stucco)  # shaded arcade: darkened stucco
    tex = Image.new("RGB", (800, 3 * FLOOR_PX))
    tex.paste(upper, (0, 0))
    tex.paste(arcade_band(800, FLOOR_PX, stucco, shadow, bays=4), (0, 2 * FLOOR_PX))
    make_tileable(tex).save(os.path.join(out_dir, "botha_chan_facade.png"))

    # Arbuckle: upper story with parapet over a ground story of the same glazing.
    tex = Image.new("RGB", (600, 2 * FLOOR_PX))
    tex.paste(rectify(arb, ARB_UPPER, (600, FLOOR_PX)), (0, 0))
    tex.paste(rectify(arb, ARB_GLASS, (600, FLOOR_PX)), (0, FLOOR_PX))
    make_tileable(tex).save(os.path.join(out_dir, "arbuckle_facade.png"))

    make_tileable(rectify(bass, ROOF, (512, 256)), 48).save(os.path.join(out_dir, "roof_tile.png"))
    make_tileable(rectify(bass, STUCCO, (256, 256)), 48).save(os.path.join(out_dir, "stucco.png"))
    print(f"textures written to {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
