"""DBL menu driver: template-match the screen, tap, wait, repeat.

SCOPE: this never plays combat. The fighting is Dragon Ball Legends' own
AUTO - PvE auto-battle, or PvP "Auto Match Rules" (Challenger League only).
This script only queues matches, claims results, dismisses popups and loops.

    python bot.py --dry        # decide, print, tap nothing
    python bot.py              # run the flow from config.json
    python bot.py --runs 5     # stop after 5 flow runs
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from wda import WDA, WDAError

BASE = Path(__file__).resolve().parent


class Bot:
    def __init__(self, cfg: dict, dry: bool = False) -> None:
        self.cfg = cfg
        self.dry = dry
        self.dev = WDA(cfg.get("wda_url") or "http://127.0.0.1:8100")
        self.templates: dict[str, np.ndarray] = {}
        self.shot: np.ndarray | None = None
        self.scale = 1.0
        self.threshold = float(cfg.get("threshold", 0.85))

    # ------------------------------------------------------------- setup
    def connect(self) -> None:
        self.dev.wait_ready(timeout=float(self.cfg.get("connect_timeout", 45)))
        self.dev.new_session(self.cfg.get("bundle_id") or None)
        self.shot = self.grab()
        pts_w, pts_h = self.dev.window_size()
        self.scale = self.shot.shape[1] / float(pts_w)
        print(
            f"[wda] screen {pts_w}x{pts_h} pt | shot "
            f"{self.shot.shape[1]}x{self.shot.shape[0]} px | scale {self.scale:.2f}x"
        )
        self.load_templates()

    def load_templates(self) -> None:
        folder = BASE / "templates"
        for path in sorted(folder.glob("*.png")):
            img = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if img is None:
                print(f"[tpl] unreadable, skipped: {path.name}")
                continue
            self.templates[path.stem] = img
        if not self.templates:
            print("[tpl] WARNING: templates/ is empty - only fixed-point steps can work")
        else:
            print(f"[tpl] {len(self.templates)}: {', '.join(sorted(self.templates))}")

    # ------------------------------------------------------------ vision
    def grab(self) -> np.ndarray:
        raw = self.dev.screenshot()
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError("could not decode the screenshot")
        return img

    def find(self, name: str):
        tpl = self.templates.get(name)
        if tpl is None or self.shot is None:
            return None, 0.0
        h, w = tpl.shape[:2]
        if h > self.shot.shape[0] or w > self.shot.shape[1]:
            return None, 0.0
        result = cv2.matchTemplate(self.shot, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(result)
        if score < self.threshold:
            return None, float(score)
        return (loc[0] + w / 2.0, loc[1] + h / 2.0), float(score)

    # ------------------------------------------------------------- input
    # Config coordinates are POINTS (what capture.py's grid shows).
    # Template centres come back in PIXELS, so they go through tap_px/swipe_px.
    def tap_pt(self, x: float, y: float) -> None:
        jitter = float(self.cfg.get("tap_jitter_pt", 0))
        if jitter:
            x += random.uniform(-jitter, jitter)
            y += random.uniform(-jitter, jitter)
        print(f"    tap {x:.1f},{y:.1f} pt")
        if not self.dry:
            self.dev.tap(x, y)

    def tap_px(self, x: float, y: float) -> None:
        self.tap_pt(x / self.scale, y / self.scale)

    def swipe_pt(self, x1, y1, x2, y2, duration: float = 0.25) -> None:
        print(f"    swipe {x1:.0f},{y1:.0f} -> {x2:.0f},{y2:.0f} pt")
        if not self.dry:
            self.dev.swipe(x1, y1, x2, y2, duration)

    def swipe_px(self, x1, y1, x2, y2, duration: float = 0.25) -> None:
        self.swipe_pt(
            x1 / self.scale, y1 / self.scale, x2 / self.scale, y2 / self.scale, duration
        )

    # ----------------------------------------------------------- helpers
    def dismiss(self) -> bool:
        for name in self.cfg.get("popups", []):
            pos, score = self.find(name)
            if pos:
                print(f"[popup] {name} ({score:.2f})")
                self.tap_px(*pos)
                time.sleep(0.6)
                self.shot = self.grab()
                return True
        return False

    def wait_for(self, name: str, timeout: float):
        deadline = time.time() + timeout
        interval = float(self.cfg.get("shot_interval", 0.4))
        while True:
            pos, score = self.find(name)
            if pos:
                return pos, score
            if self.dismiss():
                continue
            if time.time() >= deadline:
                return None, 0.0
            time.sleep(interval)
            self.shot = self.grab()

    def save_debug(self, tag: str) -> None:
        folder = BASE / "debug"
        folder.mkdir(exist_ok=True)
        path = folder / f"{tag}_{int(time.time())}.png"
        if self.shot is not None:
            cv2.imwrite(str(path), self.shot)
            print(f"[dbg] saved {path}")

    # -------------------------------------------------------------- flow
    def run_flow(self) -> bool:
        self.shot = self.grab()
        for index, step in enumerate(self.cfg.get("flow", []), 1):
            template = step.get("template")
            explicit = step.get("tap")  # points, overrides the template centre

            if template:
                pos, score = self.wait_for(template, float(step.get("timeout", 10)))
                if pos is None:
                    if step.get("optional"):
                        print(f"[bot] step {index}: '{template}' absent (optional) -> skipping")
                        continue
                    self.save_debug(f"step{index}_{template}")
                    print(f"[bot] step {index}: '{template}' not found -> run aborted")
                    return False
                print(f"[bot] step {index}: {template} ({score:.2f})")
                if explicit:
                    self.tap_pt(*explicit)
                else:
                    self.tap_px(*pos)
            elif explicit:
                print(f"[bot] step {index}: fixed point")
                self.tap_pt(*explicit)

            if "swipe" in step:
                self.swipe_pt(*step["swipe"], step.get("duration", 0.25))

            wait = float(step.get("wait", self.cfg.get("step_wait", 0.8)))
            if wait:
                time.sleep(wait)
        return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Template-driven DBL menu driver.")
    parser.add_argument("--config", default=str(BASE / "config.json"))
    parser.add_argument("--runs", type=int, default=None, help="flow runs (0 = forever)")
    parser.add_argument("--dry", action="store_true", help="print taps, send nothing")
    args = parser.parse_args(argv)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    runs = args.runs if args.runs is not None else int(cfg.get("runs", 0))

    bot = Bot(cfg, dry=args.dry)
    try:
        bot.connect()
    except WDAError as exc:
        print(f"[wda] {exc}", file=sys.stderr)
        print("      is the WDA app running on the phone and reachable at that URL?")
        return 2

    done = 0
    try:
        while runs == 0 or done < runs:
            done += 1
            suffix = "" if runs == 0 else f"/{runs}"
            print(f"\n=== run {done}{suffix} ===")
            if not bot.run_flow():
                time.sleep(float(cfg.get("fail_pause", 10)))
            time.sleep(float(cfg.get("loop_delay", 3)))
    except KeyboardInterrupt:
        print("\n[bot] stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
