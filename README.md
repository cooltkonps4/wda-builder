# dbl-ios — drive Dragon Ball Legends on an iPhone from a PC

No jailbreak. Account stays on iOS, so **Chrono Crystals are untouched**.

```
your PC (Windows)                     iPhone 12 Pro Max (iOS 26.5)
┌─────────────────────┐   USB/Wi-Fi   ┌──────────────────────────┐
│ bot.py / capture.py │ ────────────► │ WebDriverAgent (:8100)   │
│  OpenCV + requests  │ ◄──────────── │  real touch injection    │
└─────────────────────┘  screenshots  │  + DBL (foreground)      │
                                      └──────────────────────────┘
```

## 0. Why this and not the emulator

- Transferring to a different OS platform kills your Crystals: *"If you transfer
  your data to a different OS platform, your Chrono Crystals will not carry over"*
  ([Bandai FAQ](https://bnfaq.channel.or.jp/faq/detail/1924/7153)). Emulator = dead end.
- iPhone 12 Pro Max is A14, and Dopamine only covers **A14–A17 up to iOS 17.3.1**
  ([2026 jailbreak matrix](https://www.iclarified.com/jailbreak)). On iOS 26.5 there
  is no jailbreak, so AutoTouch/XXTouch (the nice on-device Lua route) is out.
- Remaining route: **WebDriverAgent** (Apple's UI-test runner) driven over HTTP.
  Note: the *Appium* layer cannot create sessions on iOS 26
  ([appium#21643](https://github.com/appium/appium/issues/21643)), which is exactly
  why this project talks to WDA directly and never installs Appium.

## 1. What it can and cannot do

**Can:** queue PvP Auto Match, flip AUTO on, wait out the fight, claim the result,
rematch, dismiss popups, loop forever. Same for PvE auto-battle farming. Also does
fixed tap/swipe sequences (menu combos, "claim all", daily routine).

**Cannot:** play combat. Polled screenshots give roughly **2–5 fps**; DBL PvP is
decided by ~0.1–0.2 s reactions (vanish on the animation, charge-step cancel).
No script wins that, and the game's own AI — which has frame-perfect input and
still loses — is the proof. Auto Match (Challenger League only) is the hands-off
ceiling the game itself offers.

**Risk:** third-party automation violates the ToS. Touch injection itself is
indistinguishable from fingers, but the automation is a ban-grounds if reviewed.
Use an account you can afford to lose.

## 2. Files

| file | purpose |
|---|---|
| `wda.py` | WDA client: screenshots, taps, swipes, home. Standalone CLI. |
| `capture.py` | screenshot + point-coordinate grid, for picking coordinates |
| `bot.py` | the flow engine (template match → tap → wait → repeat) |
| `config.json` | flow definition |
| `templates/` | your cropped reference images (see `templates/README.md`) |
| `.github/workflows/build-wda.yml` | builds an unsigned WDA `.ipa` on a free GitHub macOS runner |

## 3. Phone side

### 3a. Get WDA onto the phone
1. Push this repo to GitHub (private is fine) → **Actions → build WDA ipa → Run workflow**.
   Download the `WDA-unsigned-ipa` artifact.
2. Signulous → **Sign custom IPA** → upload → install.
3. Settings → General → VPN & Device Management → trust the certificate.
4. Settings → Privacy & Security → **Developer Mode → on** → restart. (Required on
   iOS 16+; without it WDA cannot start.)
5. Set a device passcode if you have none — the first XCUITest launch asks for it.

### 3b. Start WDA — two variants

**Simple: tap the WDA icon on the phone.** It prints `ServerURLHere -> http://<ip>:8100`.
Phone and PC on the same Wi-Fi, then `python wda.py status`.

**Robust: launch it as a test runner over USB with [go-ios](https://github.com/danielpaulus/go-ios)**
(cross-platform single binary — recommended if the server goes silent once DBL is
in the foreground, and it also forwards the port so you can ignore Wi-Fi):

```powershell
ios.exe list                      # device visible?
ios.exe devmode enable            # if not already on
ios.exe tunnel start              # iOS 17+ needs a tunnel; leave it running
ios.exe ui run wda                # or: ios.exe runwda --help for the flags
# forwards to http://127.0.0.1:8100
```
Flags drift between go-ios releases — check `ios.exe help ui run` and
`ios.exe help runwda`. If you'd rather have go-ios fetch and sign WDA itself
instead of Signulous, `ios.exe ui download` + `ios.exe ui install` does that, but
signing there needs a paid Apple Developer key (`ios.exe sign provision appstoreconnect`).

## 4. PC side

```powershell
cd dbl-ios
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt

python wda.py status              # talks to WDA
python wda.py size                # should print 428 926
python wda.py shot                # saves shots\shot_<ts>.png
python wda.py tap 214 700         # smoke-test a real touch
```

## 5. Calibrate

```powershell
python capture.py --grid          # shots\grid_<ts>.png with 50 pt labels
```
Open the grid image, note the coordinates of the buttons you care about, then crop
each button out into `templates/<name>.png` (small, distinctive, from *this* phone).
Coordinates in `config.json` are **points**, pixels in templates are matched and
converted automatically.

Fill `templates/` with the names your flow references, e.g. `nav_pvp`,
`tab_auto_match`, `btn_enter`, `btn_auto_toggle`, `btn_result_ok`, `popup_ok`.

## 6. Run

```powershell
python bot.py --dry               # prints every tap, sends nothing
python bot.py --runs 3            # three flows, then stop
python bot.py                     # forever (runs: 0 in config)
```

Failed steps dump the exact frame to `debug/` — that's what you look at when a
template stops matching after a game update.

### `config.json`

| key | meaning |
|---|---|
| `wda_url` | `http://127.0.0.1:8100` for USB/go-ios, or `http://<iphone-ip>:8100` on Wi-Fi |
| `bundle_id` | optional; only needed if you want WDA to launch DBL for you (`ios.exe apps` lists it) |
| `threshold` | template match confidence, 0.85 default; drop to 0.75 if misses |
| `shot_interval` | seconds between screenshots while waiting (~0.4 = 2.5 fps) |
| `tap_jitter_pt` | random ± points added to every tap, so taps aren't pixel-identical |
| `popups` | template names tapped automatically whenever they appear |
| `flow` | ordered steps: `template` (find+center-tap), `tap` (fixed point, in points, overrides the template centre), `swipe` (points), `wait` (seconds), `timeout`, `optional` |

## 7. Troubleshooting

| symptom | cause / fix |
|---|---|
| `cannot reach WDA` | phone locked, WDA killed, wrong IP, or firewall. USB + go-ios forward is the reliable path. |
| WDA app opens then nothing | Developer Mode off, or no passcode set. |
| WDA dies when DBL opens | foreground/normal-app suspension → launch via `ios.exe ui run wda` instead of tapping the icon. |
| `unknown command: Unhandled endpoint` on tap | some WDA builds lack `/wda/tap`; `wda.py` already falls back to the standard `/actions` API. |
| templates never match | threshold too high, crop too large, template shot at another scale/device, or UI restyled after an update. |
| taps land off-target | check the `scale` line printed at startup; re-run `capture.py` and re-read coordinates. |
| Signulous install fails / instant crash | entitlement issue with the signing cert. Then: paid Apple Developer account + `ios.exe sign` / `ui install`. |

## 8. Fallbacks

- **iPhone 11 / SE2 / XS-class (A12/A13) on iOS ≤ 26.0.1**: jailbreakable with
  Dopamine 3 → [AutoTouch](https://autotouch.net/) Lua scripts (screenshot, OCR,
  `touchDown/Move/Up`) at ~20–30 fps on-device, no PC in the loop. Same-OS device
  move keeps your Crystals. This is the strongest option that still exists.
- **Apple-silicon Mac**: the iOS build via PlayCover keeps the same CC wallet, but
  sideloading a FairPlay app is its own project — treat as an experiment.
