# Controller input profiles

Measured by suggesting each candidate path to the runtime (`tools/xr_probe_paths.py`, SteamVR 2.17.10 OpenXR runtime, API 1.0 instance).
"Accepted" means the runtime validates the path for that interaction profile; it does not prove the physical control exists in every
revision. Physical behaviour is recorded in `verification.md`.

## Accepted components per hand

| Profile | Left hand | Right hand |
|---|---|---|
| `valve/frame_controller_valve` (extension `XR_VALVE_frame_controller_interaction`) | `trigger` `squeeze` `bumper` `thumbstick` (click, touch, x, y) `dpad_up/down/left/right` `view` `system` | `trigger` `squeeze` `bumper` `thumbstick` `a` `b` `x` `y` `menu` `system` |
| `oculus/touch_controller` (Quest) | `trigger` `squeeze` `thumbstick` (click, touch, x, y) `x` `y` `menu` `thumbrest` | `trigger` `squeeze` `thumbstick` `a` `b` `system` `thumbrest` |
| `valve/index_controller` | `trigger` `squeeze` `thumbstick` `trackpad` `a` `b` `system` | same |
| `htc/vive_controller` | `trigger` `squeeze` (click) `trackpad` (click, touch, x, y) `menu` `system` | same |
| `microsoft/motion_controller` | `trigger` `squeeze` (click) `thumbstick` `trackpad` `menu` | same |

All profiles accept `grip/pose`, `aim/pose` and `output/haptic` per hand. The Steam Frame profile also accepts `shoulder` (alias of `bumper`) and `grip` as a component alias of `squeeze`.
The Meta Touch Plus/Pro and Pico 4 profiles are bound by the addon and are not measured.

## Abstract inputs used by the tools

Tools use five abstract inputs per hand (`design.md`): `trigger`, `grip`, `stick` (xy + click), `button1`, `button2`; `menu` is an extra binding.
The mapping to physical controls is data-driven per interaction profile (`profiles.py`, polled by `backends/openxr_input.py` into an `InputFrame`):

| Abstract | Quest Touch | Index | Steam Frame | Vive / WMR |
|---|---|---|---|---|
| `trigger` | `trigger/value` | `trigger/value` | `trigger/value` | `trigger/value` |
| `grip` | `squeeze/value` | `squeeze/value` | `squeeze/value` | `squeeze/click` |
| `stick` | `thumbstick` | `thumbstick` | `thumbstick` | `trackpad` (WMR: `thumbstick`) |
| `button1` | right `a`, left `x` | `a` | right `a`, left `dpad_up` | `menu` |
| `button2` | right `b`, left `y` | `b` | right `b`, left `dpad_down` | trackpad click |

The Steam Frame left controller has no face buttons; its D-pad directions act as buttons (owner-confirmed to work as buttons).
`system` is reserved by the runtime and is never used. `menu` binds to Frame left `view`, Frame right `menu`, Quest left `menu`, and is unbound on the right Quest controller. `bumper` is unbound.
The Vive trackpad is the stick without a separate stick click, because its click is `button2`; WMR uses the thumbstick for the stick and the trackpad click for `button2`.
A press starts at an analog value of 0.7 and ends below 0.3.
