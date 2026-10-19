#!/usr/bin/env python3
"""Capture + annotate in one step, as the tenant user, no Showroom iframe.

  shoot2.py NAME URL [--wait SEL] [--sleep MS] [--full]
            [--box SEL] [--box SEL] ...   red rectangle around each match
            [--click SEL]                 click before shooting
            [--scroll SEL]                scroll element into view first

Boxes are resolved from the live DOM, so no hand-measuring.
"""
import os, sys, pathlib, math
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw

OUT = pathlib.Path("/tmp/shots/raw"); OUT.mkdir(parents=True, exist_ok=True)
STATE = "/tmp/shots/state.json"
RED = (255, 0, 0)
DSF = 2


def draw_boxes(png, boxes):
    im = Image.open(png).convert("RGB")
    d = ImageDraw.Draw(im)
    sw = max(4, round(im.size[0] * 0.0045))
    for (x, y, w, h) in boxes:
        x, y, w, h = x * DSF, y * DSF, w * DSF, h * DSF
        p = sw
        d.rectangle([x - p, y - p, x + w + p, y + h + p], outline=RED, width=sw)
    im.save(png)
    return len(boxes), sw


def main():
    name, url = sys.argv[1], sys.argv[2]
    a = sys.argv[3:]
    wait_sel = sleep_ms = None
    full = False
    box_sels, click_sels, scroll_sel = [], [], None
    clickxy = []
    i = 0
    while i < len(a):
        if a[i] == "--wait": wait_sel = a[i+1]; i += 2
        elif a[i] == "--sleep": sleep_ms = int(a[i+1]); i += 2
        elif a[i] == "--full": full = True; i += 1
        elif a[i] == "--box": box_sels.append(a[i+1]); i += 2
        elif a[i] == "--click": click_sels.append(a[i+1]); i += 2
        elif a[i] == "--scroll": scroll_sel = a[i+1]; i += 2
        elif a[i] == "--clickxy": clickxy.append(tuple(float(v) for v in a[i+1].split(","))); i += 2
        else: i += 1

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        ctx = b.new_context(viewport={"width":1600,"height":1000},
                            device_scale_factor=DSF, ignore_https_errors=True,
                            storage_state=STATE if os.path.exists(STATE) else None)
        pg = ctx.new_page()
        pg.goto(url, wait_until="domcontentloaded")
        if wait_sel:
            try: pg.wait_for_selector(wait_sel, timeout=40000)
            except Exception as e: print("  wait:", str(e)[:70])
        for (cx, cy) in clickxy:
            pg.mouse.click(cx, cy); pg.wait_for_timeout(2500)
        for cs in click_sels:
            try:
                pg.locator(cs).first.click(timeout=15000); pg.wait_for_timeout(3000)
            except Exception as e: print("  click failed:", cs, str(e)[:60])
        if scroll_sel:
            try: pg.locator(scroll_sel).first.scroll_into_view_if_needed(timeout=10000); pg.wait_for_timeout(800)
            except Exception as e: print("  scroll:", str(e)[:60])
        pg.wait_for_timeout(sleep_ms if sleep_ms else 2500)

        boxes = []
        for bs in box_sels:
            try:
                loc = pg.locator(bs).first
                loc.scroll_into_view_if_needed(timeout=8000)
                pg.wait_for_timeout(500)
                bb = loc.bounding_box()
                if bb: boxes.append((bb["x"], bb["y"], bb["width"], bb["height"]))
                else: print("  no bbox:", bs)
            except Exception as e:
                print("  box failed:", bs, str(e)[:60])

        out = OUT / f"{name}.png"
        pg.screenshot(path=str(out), full_page=full)
        ctx.storage_state(path=STATE)
        b.close()

    n, sw = draw_boxes(out, boxes) if boxes else (0, 0)
    print(f"  {out.name}  boxes={n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

