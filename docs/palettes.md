# Design-system palettes

**Single source:** `THEME_VARS` in `frontend/js/01-app-core.js`. This
file, the palette blocks + `.theme-tile--*` faces in
`frontend/styles-tokens.css`, and `frontend/palettes.json` are all
**generated** from that one table by `scripts/gen_theme_css.py`.
Edit the table, then run:

```bash
python3 scripts/gen_theme_css.py   # --check fails CI on drift
```

## How the blocks are shaped (and why)

* **dark / light** are full-set `[data-theme="..."]` blocks that also
  match `<body>`. That body pin is load-bearing: it is what keeps a
  saved custom accent *inert* in the two default themes, exactly as
  the app behaved before the token system existed.
* **The six exotic palettes** are `html[data-theme="..."]` blocks
  carrying only the tokens that differ from the `:root` base. No body
  pin, so a custom accent stays *visible* there — also the
  pre-existing behaviour, deliberately preserved.
* Unknown theme ids resolve to the dark base and warn.

## Contrast methodology

WCAG 2.x relative luminance, measured per pair. Text tokens are
measured on `bg2` — the card/header surface the text ramp actually
sits on. Translucent `rgba()` borders have no single ratio and are
excluded. The weakest pairing of each palette is noted below. WCAG AA
is 4.5:1 for body text and 3:1 for large text; the `onAccent`-on-`accent`
pair is button-label text (large/bold by construction), so a value
between 3 and 4.5 there is AA-large-compliant, not a body-text failure.

## Light (`light`)

The default light palette. Body-pinned full-set block: a saved custom accent stays inert (pre-existing behaviour, deliberately preserved).

| Token | Value | | Pair | Ratio |
|---|---|---|---|---|
| `--bg-0` | #ffffff | | `text0 on bg2` | **16.12:1** |
| `--bg-1` | #f9fafb | | `text1 on bg2` | **9.37:1** |
| `--bg-2` | #f3f4f6 | | `text2 on bg2` | **5.26:1** |
| `--bg-3` | #e5e7eb | | `text3 on bg2` | **5.34:1** |
| `--bg-4` | #d1d5db | | `accentText on bg2` | **5.42:1** |
| `--bg-5` | #9ca3af | | `onAccent on accent` | **4.58:1** |
| `--text-0` | #111827 | |  |  |
| `--text-1` | #374151 | |  |  |
| `--text-2` | #5f6672 | |  |  |
| `--text-3` | #5d6573 | |  |  |
| `--border` | rgba(0,0,0,0.08) | |  |  |
| `--border-hi` | rgba(0,0,0,0.15) | |  |  |
| `--accent` | #6a6df2 | |  |  |
| `--accent-hi` | #4f46e5 | |  |  |
| `--accent-text` | #02699f | |  |  |
| `--on-accent` | #0b1020 | |  |  |
| `--accent-glow` | rgba(99,102,241,0.1) | |  |  |

Weakest pair: **onAccent on accent at 4.58:1** (AA ✓)

## Dark (`dark`)

The default dark palette — what :root carries, measured as rendered. Body-pinned full-set block: a saved custom accent stays inert.

| Token | Value | | Pair | Ratio |
|---|---|---|---|---|
| `--bg-0` | #0f0f0f | | `text0 on bg2` | **15.29:1** |
| `--bg-1` | #171717 | | `text1 on bg2` | **11.25:1** |
| `--bg-2` | #1e1e1e | | `text2 on bg2` | **6.38:1** |
| `--bg-3` | #2a2a2a | | `text3 on bg2` | **5.50:1** |
| `--bg-4` | #363636 | | `accentText on bg2` | **5.59:1** |
| `--bg-5` | #444444 | | `onAccent on accent` | **4.58:1** |
| `--text-0` | #f5f5f5 | |  |  |
| `--text-1` | #d4d4d4 | |  |  |
| `--text-2` | #a0a0a0 | |  |  |
| `--text-3` | #949494 | |  |  |
| `--border` | rgba(255,255,255,0.08) | |  |  |
| `--border-hi` | rgba(255,255,255,0.15) | |  |  |
| `--accent` | #6a6df2 | |  |  |
| `--accent-hi` | #818cf8 | |  |  |
| `--accent-text` | #818cf8 | |  |  |
| `--on-accent` | #0b1020 | |  |  |
| `--accent-glow` | rgba(99,102,241,0.15) | |  |  |

Weakest pair: **onAccent on accent at 4.58:1** (AA ✓)

## Obsidian (`obsidian`)

Deep blue-black with a sky accent. html-scoped diff-only block: a custom accent stays visible.

| Token | Value | | Pair | Ratio |
|---|---|---|---|---|
| `--bg-0` | #040408 | | `text0 on bg2` | **19.30:1** |
| `--bg-1` | #06060d | | `text1 on bg2` | **13.00:1** |
| `--bg-2` | #0d0d18 | | `text2 on bg2` | **5.56:1** |
| `--bg-3` | #16162a | | `text3 on bg2` | **5.19:1** |
| `--bg-4` | #22223c | | `accentText on bg2` | **9.01:1** |
| `--bg-5` | #2e2e52 | | `onAccent on accent` | **8.84:1** |
| `--text-0` | #ffffff | |  |  |
| `--text-1` | #cbd5e1 | |  |  |
| `--text-2` | #7a8aaa | |  |  |
| `--text-3` | #7384ae | |  |  |
| `--border` | rgba(255,255,255,.1) | |  |  |
| `--border-hi` | rgba(255,255,255,.2) | |  |  |
| `--accent` | #38bdf8 | |  |  |
| `--accent-hi` | #7dd3fc | |  |  |
| `--accent-text` | #38bdf8 | |  |  |
| `--on-accent` | #0b1020 | |  |  |
| `--accent-glow` | #38bdf822 | |  |  |

Weakest pair: **text3 on bg2 at 5.19:1** (AA ✓)

## Jet (`jet`)

Pure black with a crimson accent. html-scoped diff-only block: a custom accent stays visible.

| Token | Value | | Pair | Ratio |
|---|---|---|---|---|
| `--bg-0` | #000000 | | `text0 on bg2` | **18.69:1** |
| `--bg-1` | #0a0a0a | | `text1 on bg2` | **15.16:1** |
| `--bg-2` | #121216 | | `text2 on bg2` | **7.29:1** |
| `--bg-3` | #1a1a20 | | `text3 on bg2` | **5.04:1** |
| `--bg-4` | #24242e | | `accentText on bg2` | **4.98:1** |
| `--bg-5` | #30303e | | `onAccent on accent` | **4.70:1** |
| `--text-0` | #ffffff | |  |  |
| `--text-1` | #e2e8f0 | |  |  |
| `--text-2` | #94a3b8 | |  |  |
| `--text-3` | #76869d | |  |  |
| `--border` | rgba(255,255,255,.15) | |  |  |
| `--border-hi` | rgba(255,255,255,.3) | |  |  |
| `--accent` | #e11d48 | |  |  |
| `--accent-hi` | #fb7185 | |  |  |
| `--accent-text` | #e8496c | |  |  |
| `--on-accent` | #ffffff | |  |  |
| `--accent-glow` | #e11d4822 | |  |  |

Weakest pair: **onAccent on accent at 4.70:1** (AA ✓)

## Midnight Blue (`midnight`)

Navy ramp with a violet accent. html-scoped diff-only block: a custom accent stays visible.

| Token | Value | | Pair | Ratio |
|---|---|---|---|---|
| `--bg-0` | #050810 | | `text0 on bg2` | **17.80:1** |
| `--bg-1` | #080b14 | | `text1 on bg2` | **11.82:1** |
| `--bg-2` | #0f1220 | | `text2 on bg2` | **5.36:1** |
| `--bg-3` | #161b30 | | `text3 on bg2` | **5.15:1** |
| `--bg-4` | #202848 | | `accentText on bg2` | **5.10:1** |
| `--bg-5` | #2d3764 | | `onAccent on accent` | **4.78:1** |
| `--text-0` | #f8fafc | |  |  |
| `--text-1` | #c2ceec | |  |  |
| `--text-2` | #7a8aaa | |  |  |
| `--text-3` | #7885b4 | |  |  |
| `--border` | rgba(168,85,247,.16) | |  |  |
| `--border-hi` | rgba(168,85,247,.3) | |  |  |
| `--accent` | #a855f7 | |  |  |
| `--accent-hi` | #c084fc | |  |  |
| `--accent-text` | #ad5ff7 | |  |  |
| `--on-accent` | #0b1020 | |  |  |
| `--accent-glow` | #a855f722 | |  |  |

Weakest pair: **onAccent on accent at 4.78:1** (AA ✓)

## Forest Emerald (`forest`)

Green-on-green ramp. html-scoped diff-only block: a custom accent stays visible.

| Token | Value | | Pair | Ratio |
|---|---|---|---|---|
| `--bg-0` | #06100a | | `text0 on bg2` | **15.83:1** |
| `--bg-1` | #09160e | | `text1 on bg2` | **13.00:1** |
| `--bg-2` | #0e2216 | | `text2 on bg2` | **10.94:1** |
| `--bg-3` | #14301f | | `text3 on bg2` | **8.68:1** |
| `--bg-4` | #1d452d | | `accentText on bg2` | **6.58:1** |
| `--bg-5` | #275e3d | | `onAccent on accent` | **7.46:1** |
| `--text-0` | #ecfdf5 | |  |  |
| `--text-1` | #a7f3d0 | |  |  |
| `--text-2` | #6ee7b7 | |  |  |
| `--text-3` | #34d399 | |  |  |
| `--border` | rgba(16,185,129,.16) | |  |  |
| `--border-hi` | rgba(16,185,129,.3) | |  |  |
| `--accent` | #10b981 | |  |  |
| `--accent-hi` | #34d399 | |  |  |
| `--accent-text` | #10b981 | |  |  |
| `--on-accent` | #0b1020 | |  |  |
| `--accent-glow` | #10b98122 | |  |  |

Weakest pair: **accentText on bg2 at 6.58:1** (AA ✓)

## Ember (`ember`)

Warm charcoal with a flame accent. Added in #258 — onboarding offered it as a swatch long before it existed. html-scoped diff-only block.

| Token | Value | | Pair | Ratio |
|---|---|---|---|---|
| `--bg-0` | #100a08 | | `text0 on bg2` | **16.51:1** |
| `--bg-1` | #170f0b | | `text1 on bg2` | **12.11:1** |
| `--bg-2` | #1f1410 | | `text2 on bg2` | **6.84:1** |
| `--bg-3` | #2a1a14 | | `text3 on bg2` | **5.35:1** |
| `--bg-4` | #38221a | | `accentText on bg2` | **8.55:1** |
| `--bg-5` | #482e22 | | `onAccent on accent` | **7.52:1** |
| `--text-0` | #fef3ec | |  |  |
| `--text-1` | #e8cfc0 | |  |  |
| `--text-2` | #b39b8a | |  |  |
| `--text-3` | #9d8879 | |  |  |
| `--border` | rgba(240,136,80,.16) | |  |  |
| `--border-hi` | rgba(240,136,80,.3) | |  |  |
| `--accent` | #f08850 | |  |  |
| `--accent-hi` | #f8a878 | |  |  |
| `--accent-text` | #f49e6e | |  |  |
| `--on-accent` | #1a0e06 | |  |  |
| `--accent-glow` | #f0885022 | |  |  |

Weakest pair: **text3 on bg2 at 5.35:1** (AA ✓)

## Ocean (`ocean`)

Deep teal-sea ramp with a cyan accent. Added in #258, same story as ember. html-scoped diff-only block.

| Token | Value | | Pair | Ratio |
|---|---|---|---|---|
| `--bg-0` | #080d10 | | `text0 on bg2` | **16.28:1** |
| `--bg-1` | #0c1418 | | `text1 on bg2` | **11.97:1** |
| `--bg-2` | #111c22 | | `text2 on bg2` | **7.49:1** |
| `--bg-3` | #16262e | | `text3 on bg2` | **5.77:1** |
| `--bg-4` | #1d3340 | | `accentText on bg2` | **9.42:1** |
| `--bg-5` | #264553 | | `onAccent on accent` | **8.78:1** |
| `--text-0` | #effafc | |  |  |
| `--text-1` | #c2dbe2 | |  |  |
| `--text-2` | #8fb0ba | |  |  |
| `--text-3` | #7a9aa6 | |  |  |
| `--border` | rgba(56,197,216,.16) | |  |  |
| `--border-hi` | rgba(56,197,216,.3) | |  |  |
| `--accent` | #38c5d8 | |  |  |
| `--accent-hi` | #6fdbe8 | |  |  |
| `--accent-text` | #4fd0e0 | |  |  |
| `--on-accent` | #06181c | |  |  |
| `--accent-glow` | #38c5d822 | |  |  |

Weakest pair: **text3 on bg2 at 5.77:1** (AA ✓)

