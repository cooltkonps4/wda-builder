"""Grab a screenshot from the phone, print its geometry, optionally draw a grid.

The bot works in POINTS (iOS logical units), while screenshots are in PIXELS
(iPhone 12 Pro Max: 428x926 pt, 1284x2778 px, 3x). This helper shows both and
draws a labelled grid in points so you can read coordinates straight off the
image.

    python capture.py                 # save a plain screenshot
    python capture.py --grid          # save screenshot + 50pt grid overlay
    python capture.py --grid --step 25

Crop your reference images out of these PNGs into templates/<name>.png.
"""

from __future__ import annotations

import argparse
import sys
import time

import cv2
import numpy as np

from wda import DEFAULT_URL, SHOTS, connect


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Screenshot + coordinate grid helper.")
    parser.add_argument("--url", default=DEFAULT_URL, help="WDA base URL")
    parser.add_argument("--grid", action="store_true", help="write a grid overlay too")
    parser.add_argument("--step", type=int, default=50, help="grid spacing in points")
    args = parser.parse_args(argv)

    dev = connect(args.url)
    pts_w, pts_h = dev.window_size()
    raw = dev.screenshot()
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        print("could not decode screenshot", file=sys.stderr)
        return 2

    px_h, px_w = img.shape[:2]
    scale = px_w / float(pts_w)

    SHOTS.mkdir(exist_ok=True)
    stamp = int(time.time())
    plain = SHOTS / f"shot_{stamp}.png"
    cv2.imwrite(str(plain), img)

    print(f"points : {pts_w} x {pts_h}")
    print(f"pixels : {px_w} x {px_h}")
    print(f"scale  : {scale:.2f}")
    print(f"saved  : {plain}")

    if args.grid:
        grid = img.copy()
        colour = (0, 255, 255)
        for x in range(0, pts_w + 1, args.step):
            px = int(round(x * scale))
            cv2.line(grid, (px, 0), (px, px_h), colour, 1)
            cv2.putText(grid, str(x), (px + 3, 18), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(grid, str(x), (px + 3, 18), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, colour, 1, cv2.LINE_AA)
        for y in range(0, pts_h + 1, args.step):
            px = int(round(y * scale))
            cv2.line(grid, (0, px), (px_w, px), colour, 1)
            cv2.putText(grid, str(y), (3, px - 4), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(grid, str(y), (3, px - 4), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, colour, 1, cv2.LINE_AA)
        out = SHOTS / f"grid_{stamp}.png"
        cv2.imwrite(str(out), grid)
        print(f"grid   : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
