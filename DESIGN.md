---
name: 待辦小幫手 · 文字風暴
description: 黑白字詞頁框與可核對的 LINE Bot 改善紀錄。
colors:
  paper: "#f6f6f6"
  ink: "#0a0a0a"
  secondary: "#616265"
  rule: "#bfc2c7"
  panel: "#e7e8eb"
  body-muted: "#515356"
  version: "#747a82"
  comparison-rule: "#b2b6bc"
  comparison-top: "#b8bec4"
typography:
  display:
    fontFamily: "'Noto Sans TC', sans-serif"
    fontSize: "15.75vw"
    fontWeight: 900
    lineHeight: 1
    letterSpacing: "-.04em"
  headline:
    fontFamily: "'Noto Sans TC', sans-serif"
    fontSize: "3.056vw"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-.015em"
  section:
    fontFamily: "'Noto Sans TC', sans-serif"
    fontSize: "clamp(28px,2.8vw,42px)"
    fontWeight: 700
  title:
    fontFamily: "'Noto Sans TC', sans-serif"
    fontSize: "22px"
    fontWeight: 700
  body:
    fontFamily: "'Noto Sans TC', sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.8
  label:
    fontFamily: "'Noto Sans TC', sans-serif"
    fontSize: "1.063vw"
    lineHeight: 1.4
  reply:
    fontFamily: "'Noto Sans TC', sans-serif"
    fontSize: "1.263vw"
    fontWeight: 400
    lineHeight: 1.65
  evidence:
    fontFamily: "'Noto Sans TC', sans-serif"
    fontSize: "17px"
    lineHeight: 1.65
  log:
    fontFamily: "'Noto Sans TC', sans-serif"
    fontSize: "14px"
    lineHeight: 1.6
rounded:
  square: "0"
spacing:
  small: "8px"
  mobile-gap: "16px"
  inset: "20px"
  disclosure: "24px"
  mobile-section: "32px"
  column: "5vw"
components:
  reply:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    typography: "{typography.reply}"
  reply-mobile:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.square}"
    padding: "14px"
  evidence-header:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
  log:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    padding: "20px"
    typography: "{typography.log}"
---

# Design System: 待辦小幫手 · 文字風暴

## Overview

**Creative North Star: "文字風暴 / Alphabet Storm"**

The user selected the official Impeccable world with seed 45547134 and approved C「前後校訂」. Huge native Chinese words dissolve into small native glyphs; black ink, silver-gray panels and open fine rules frame selectable evidence. The storm belongs to the decorative header, while reading content stays stable and clear.

The implemented source is `docs/index.html` and `docs/styles.css`. This system covers the current development-record page and related new surfaces. The preserved `docs/v1/` first-version archive keeps its original design; neither its older stylesheet nor the older green documentation defines the current world. The approved first-viewport composition remains a surface decision in `.impeccable/surfaces/docs-index-html.md`, rather than a required layout for every future screen.

**Key Characteristics:**
- Native, selectable Chinese reading text and decorative glyph spans.
- Paper, black ink and silver-gray structure; open square surfaces.
- Finite hover movement confined to the header, with reduced-motion support.
- Written evidence status and preserved first-version records.

## Colors

The palette is monochrome. Frontmatter preserves actual source values, including contextual grays.

### Primary
- **Black ink** (`ink`): display words, headings, reading text, selection background and keyboard outlines.

### Neutral
- **Paper** (`paper`): the page ground and selection foreground.
- **Silver gray** (`panel`): response evidence, table headers and raw-log backgrounds.
- **Quiet gray** (`secondary`): metadata, source notes, hovered links and some scattered glyphs.
- **Reading gray** (`body-muted`): short explanatory body copy in the first viewport.
- **Fine gray** (`rule`): section, table and footer divisions.
- **Version gray** (`version`): comparison version labels; navigation version is overridden to quiet gray.
- **Comparison grays** (`comparison-rule`, `comparison-top`): the horizontal comparison and supporting rules.

**The Written Status Rule.** Keep “本機” and “LINE 真人對話測試：待完成” explicit; tonal hierarchy cannot imply completed live testing.

## Typography

**Display and Body Font:** self-hosted variable Noto Sans TC with a generic sans-serif fallback. The font face declares weights (100–900), uses `font-display: swap`, and loads `docs/fonts/noto-sans-tc.woff2`. Code inherits this family, with tabular numerals; this system does not introduce a separate monospace font.

The bundled file is a page-specific subset (136,060 bytes), accompanied by `docs/fonts/OFL.txt`. New copy may introduce unsupported characters and fall back to another sans-serif; regenerate and verify the subset when expanding the repertoire, retaining the license.

### Hierarchy
- **Display:** enormous decorative 記錄 / 查詢 words, compressed horizontally (`scaleX(.89)`) and shifted upward (`translateY(-.12em)`).
- **Headline:** the formal document title; it remains native text and is the accessible heading.
- **Comparison:** headings and version labels use (2.126vw); the shared input uses (1.927vw, weight 700).
- **Section / title:** lower-content headings and subheadings use their frontmatter roles. First-viewport supporting headings use (1.462vw, weight 700, line-height 1.35).
- **Body:** lower-content reading text is constrained to (75ch). First-viewport explanation uses (1.196vw, line-height 1.6); introduction uses (1.595vw).
- **Reply:** first-version reply uses the frontmatter role; improved reply remains (1.395vw, line-height 1.4).
- **Label / evidence / log:** metadata is compact; the detailed evidence table uses the evidence role, and raw logs use the log role.

**The Native Text Rule.** Keep reading content selectable and semantic; decorative glyphs are `aria-hidden`, not substitutes for accessible headings or evidence.

## Layout

Desktop uses a proportional first viewport (aspect ratio 1505/1045) with source-defined absolute regions expressed in viewport-relative coordinates. The masthead sits in normal page content and is not sticky. The large word field precedes the title and shared input; a two-column first-version/improved-version comparison leads to open explanatory and compact evidence regions. This precise composition is specific to the approved page.

Lower content returns to normal document flow with maximum width (1505px), padding (4vw 3vw), section padding (3vw 0), and equal two-column reading/evidence grids with gap (5vw). Detailed table cells use (16px 12px) padding. Footer uses (3vw) padding and a spaced flex layout.

At **max-width (700px)**, the first viewport becomes an intrinsic-height two-column grid with equal `minmax(0,1fr)` tracks, (16px) column gap, (10px) row gap and padding (16px 20px 28px). Navigation and word marks retain paired rows; substantive reading and comparison responses span both tracks, with first-version and improved-version evidence stacked sequentially. Word marks use (24vw), horizontal compression (.83), and line-height (1.3); the formal title is (28px, line-height 1.4), comparison headings (23px), response and body text (16px), and metadata (13–14px). Glyph regions narrow, fade to opacity (.6), and their individual type sizes become (7px).

Mobile lower content uses padding (0 20px 30px), section padding (32px 0), headings (27px) and body (16px). Reading grids become blocks. The compact first-viewport table remains tabular (12px); the detailed table becomes block rows (15px), hides its header and displays each cell's written `data-label`. Its caption is a full-width block. Footer stacks with padding (24px 20px). No additional tablet breakpoint or sticky offset is implemented.

## Elevation & Depth

There are no shadows. Depth comes from typography scale, silver panels and thin borders. The header is an open page field rather than an elevated navigation layer. Selection inverts ink and paper; keyboard focus uses an ink outline (2px), offset (4px).

**The Flat Paper Rule.** Use square, flat evidence surfaces and fine rules; do not introduce lifted or rounded cards into this approved world.

## Shapes

Rectangular panels and straight rules have square corners. The favicon is a square black tile with a white SVG check. Link arrows are native inline SVG with consistent thin strokes (1.5), round caps and joins; they are visual companions to written link labels, not glyph icons. Desktop arrows size to (1.86vw × 1.33vw); mobile uses (25px × 20px).

## Components

### Navigation and evidence links

Text links inherit ink, with underline thickness (1px) and offset (5px); hover changes to quiet gray. Navigation removes default underlining while the current item is underlined with offset (10px). The skip link appears on keyboard focus. Arrow links are flex rows with gap (1.1vw), becoming (12px) mobile. No application buttons or editable fields are implemented.

### Native word storm

The header uses 599 decorative glyph spans, positioned as source-defined particles beside oversized native words. It uses no JavaScript, raster, canvas rendering or perpetual animation. A header hover shifts selected spans only (3px, −2px) or (2px, 3px), transitioning transform over (1.1s cubic-bezier(.16,1,.3,1)); leaving hover restores rest. Reduced-motion removes both transition and displacement. Smooth anchor scrolling likewise becomes automatic with reduced-motion.

### Comparison replies

Both versions use the same silver-gray evidence material, keeping the changed reply itself central. Newlines are preserved. Desktop reply text overlays source-positioned panels; mobile replies have intrinsic height and inset (14px). These are actual program responses, not a LINE client mockup.

### Evidence table and status

Tables use fine bottom rules and silver headers. The compact table also uses vertical cell dividers; the detailed table uses top-aligned cells and written “通過 · 本機” labels. The live-test region uses two fine horizontal borders and explicitly identifies pending work. The latest-10 query behavior and 14 passing local tests are content facts, not implied live evidence.

### Raw-log disclosure and archive

Native `details` / `summary` preserves keyboard interaction. Summary padding is (16px 0); logs wrap long text, use inset (20px), and raw logs scroll within maximum height (500px). Archive links remain ordinary list links to preserved first-version resources; do not restyle or overwrite archived documents to make them match the new page.

## Do's and Don'ts

### Do:
- **Do** preserve native text, semantic headings, selectable replies and visible keyboard focus.
- **Do** confine glyph movement to the decorative header and honor reduced-motion.
- **Do** keep actual input, expected reply, actual reply and written local/live status adjacent.
- **Do** update the font subset when new characters require it and retain the OFL license.
- **Do** preserve the first-version archive and its original visual system.

### Don't:
- **Don't** add colorful, rounded or shadowed cards to this approved monochrome world.
- **Don't** replace native evidence with images, canvas, perpetual animation or decorative glyph icons.
- **Don't** turn the selected desktop composition into a universal rule for unrelated surfaces.
- **Don't** present local test output, substitute APIs or design drafts as completed LINE真人測試.
- **Don't** claim deployment or publication validation from this documentation pass.
