#!/usr/bin/env python3
"""Draw James-style red callouts on a screenshot.

Matches the existing Module 2 convention: a thick pure-red rectangle around
the thing to click, and an optional arrow when the target is small.

  annotate.py in.png out.png box=x,y,w,h [box=...] [arrow=x1,y1,x2,y2]

Coordinates are in CSS pixels (the same space Playwright reports from
bounding_box()), and are scaled automatically if the PNG was captured at a
device pixel ratio > 1.
"""
import sys
from PIL import Image, ImageDraw

RED = (255, 0, 0)


def stroke_for(width: int) -> int:
    # James's captures: ~6px on 1495px wide. Keep it proportional but legible.
    return max(3, round(width * 0.0045))


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    im = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(im)
    w, _ = im.size
    sw = stroke_for(w)

    # scale= lets the caller pass CSS px while the PNG is @2x
    scale = 1.0
    for arg in sys.argv[3:]:
        if arg.startswith("scale="):
            scale = float(arg.split("=", 1)[1])

    for arg in sys.argv[3:]:
        if arg.startswith("box="):
            x, y, bw, bh = (float(v) * scale for v in arg[4:].split(","))
            # pad slightly so the stroke sits outside the element
            p = sw
            d.rectangle([x - p, y - p, x + bw + p, y + bh + p],
                        outline=RED, width=sw)
        elif arg.startswith("arrow="):
            x1, y1, x2, y2 = (float(v) * scale for v in arg[6:].split(","))
            d.line([x1, y1, x2, y2], fill=RED, width=sw + 2)
            # arrowhead
            import math
            ang = math.atan2(y2 - y1, x2 - x1)
            hl = sw * 6
            for off in (2.6, -2.6):
                d.line([x2, y2,
                        x2 - hl * math.cos(ang + off),
                        y2 - hl * math.sin(ang + off)],
                       fill=RED, width=sw + 2)
    im.save(dst)
    print(f"{dst} ({im.size[0]}x{im.size[1]}, stroke {sw})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
