---
name: "pixel-art"
description: "Generate pixel art SVG illustrations for READMEs, docs, or slides. Use when user says \"\u753b\u50cf\u7d20\u56fe\", \"pixel art\", \"make an SVG illustration\", \"README hero image\", or wants a cute visual."
---

# Pixel Art SVG Generator

Create a pixel art SVG illustration: $ARGUMENTS

## Design Principles

### Pixel Grid
- Each "pixel" is a `<rect>` with width/height of 7px
- Grid spacing: 7px (no gaps between pixels)
- Characters are typically 8-10 pixels wide, 8-12 pixels tall
- Use `<g transform="translate(x,y)">` to position and reuse character groups

### Color Palette
Keep it simple — 3-5 colors per character:
- **Skin**: `#FFDAB9` (light), `#E8967A` / `#D4956A` (blush/shadow)
- **Eyes**: `#333`
- **Hair**: `#8B5E3C` (brown), `#2C2C2C` (black), `#FFD700` (blonde), `#C0392B` (red)
- **Clothes**: use project's brand color (e.g. `#4A9EDA` for blue, `#74AA63` for green)
- **Shoes/pants**: `#444`
- **Accessories**: `#555` (glasses frames), `#FFD700` (crown)

### Character Template (7px grid)
```
Row 0 (hair top):     4 pixels centered
Row 1 (hair):         6 pixels wide
Row 2 (face top):     6 pixels — all skin
Row 3 (eyes):         6 pixels — skin, eye, skin, skin, eye, skin
Row 4 (mouth):        6 pixels — skin, skin, mouth, mouth, skin, skin
Row 5 (body top):     8 pixels — hand, 6 shirt, hand
Row 6 (body):         6 pixels — all shirt
Row 7 (legs):         2+2 pixels — with gap in middle
```

### Scene Composition

#### Chat Dialogue Layout (like our hero image)
- Two characters on left/right sides, vertically centered
- Chat bubbles between them, alternating left/right
- Bubble tails point toward the speaking character
- Arrows between bubbles show direction of communication
- Use `orient="auto"` markers for arrow heads
- Bottom: tagline or decoration

#### Single Character with Label
- Character centered
- Label text below
- Optional: speech bubble above

#### Group Scene
- Characters spaced evenly
- Optional: ground line, background elements
- Keep viewBox tight — no wasted space

### SVG Structure
```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 W H" font-family="monospace">
  <defs>
    <!-- Arrow markers if needed -->
  </defs>

  <rect width="W" height="H" fill="#fafbfc" rx="12"/>  <!-- Background -->

  <!-- Characters via <g transform="translate(...)"> -->
  <!-- Dialogue bubbles: <rect> + <polygon> tail + <text> -->
  <!-- Arrows: <line> with marker-end -->
  <!-- Labels: <text> with text-anchor="middle" -->
</svg>
```

### Chat Bubble Recipe
```xml
<!-- Blue bubble (left character speaks) -->
<rect x="110" y="29" width="280" height="26" fill="#e8f4fd" stroke="#4a9eda" stroke-width="1.5" rx="8"/>
<!-- Tail pointing left toward character -->
<polygon points="108,41 99,47 108,46" fill="#e8f4fd" stroke="#4a9eda" stroke-width="1.5"/>
<rect x="107" y="40" width="3" height="7" fill="#e8f4fd"/>  <!-- covers stroke at junction -->
<text x="123" y="46" font-size="13px">📄 Message here</text>

<!-- Orange bubble (right character responds) -->
<rect x="490" y="71" width="280" height="26" fill="#fdf2e8" stroke="#da8a4a" stroke-width="1.5" rx="8"/>
<!-- Tail pointing right toward character -->
<polygon points="772,83 781,89 772,88" fill="#fdf2e8" stroke="#da8a4a" stroke-width="1.5"/>
<rect x="770" y="82" width="3" height="7" fill="#fdf2e8"/>
<text x="503" y="88" font-size="13px">🤔 Response here</text>
```

### Arrow Recipe
```xml
<defs>
  <marker id="ar" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
    <polygon points="0 0, 8 3, 0 6" fill="#4a9eda"/>
  </marker>
</defs>
<!-- Right arrow (→): x1 < x2 -->
<line x1="392" y1="42" x2="465" y2="42" stroke="#4a9eda" stroke-width="2" marker-end="url(#ar)"/>
<!-- Left arrow (←): x1 > x2 -->
<line x1="488" y1="84" x2="420" y2="84" stroke="#da8a4a" stroke-width="2" marker-end="url(#ar-o)"/>
```

## Workflow

### Step 1: Understand the Request
- What characters/objects to draw?
- What's the scene? (dialogue, portrait, group, diagram)
- What colors/brand to match?
- What size? (compact for badge, wide for README hero)

### Step 2: Generate SVG
- Write to a temp file or project directory
- Open with a local preview command for visual inspection
- Keep viewBox tight — measure actual content bounds

### Step 3: Iterate with User
- User provides feedback on screenshot
- Common fixes: overlap, arrow direction, spacing, sizing
- Use `Edit` for small tweaks, `Write` for major redesigns
- Typical: 2-4 iterations to get it right

### Step 4: Finalize
- Ensure no personal info in the SVG
- Clean up: remove unused defs, tighten viewBox
- Suggest adding to README: `![Alt text](filename.svg)`

## Capability Rule

If the user expects local preview or interactive visual iteration and the current environment cannot open or preview the generated asset, stop and tell the user what needs to be configured. Do not silently downgrade into a write-only path unless the user explicitly asked for that mode.

## Common Pitfalls
- **Arrow direction**: `orient="auto"` follows line direction. Line going right→left = arrowhead points left
- **Bubble overlap**: keep 38-44px vertical spacing between rows
- **Text overflow**: monospace 13px ≈ 7.8px/char, emoji ≈ 14px. Measure before setting bubble width
- **Character overlap with bubbles**: keep character x-zone and bubble x-zone separated by ≥10px
- **viewBox too large**: match viewBox to actual content, add ~10px padding
- **Tail stroke artifact**: always add a small `<rect>` at the bubble-tail junction to cover the stroke line
