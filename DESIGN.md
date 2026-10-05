---
name: 待辦小幫手
description: 清楚閱讀、核對前後差異與測試證據的開發紀錄。
colors:
  primary: "#15634E"
  ink: "#14251F"
  surface: "#FFFFFF"
  tint: "#EDF3EE"
  muted: "#52675E"
  line: "#DCE6E0"
  primary-hover: "#0B4736"
  focus: "#428A6B"
  comparison-improved: "#E6F0E9"
  comparison-divider: "#BFD6C9"
  comparison-header: "#F2F5F3"
  comparison-surface: "#F8FBF9"
  reply-surface: "#EFF3F0"
  code-surface: "#F0F4F1"
  footer-surface: "#F6F9F7"
typography:
  display:
    fontFamily: '"PingFang TC", "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif'
    fontSize: "44px"
    fontWeight: 750
    lineHeight: 1.25
    letterSpacing: "-.025em"
  headline:
    fontFamily: '"PingFang TC", "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif'
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "-.02em"
  title:
    fontFamily: '"PingFang TC", "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif'
    fontSize: "20px"
    fontWeight: 650
    lineHeight: 1.5
  body:
    fontFamily: '"PingFang TC", "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.8
  label:
    fontFamily: '"PingFang TC", "Noto Sans TC", "Microsoft JhengHei", system-ui, sans-serif'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.8
  log:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "14px"
    lineHeight: 1.65
rounded:
  surface: "4px"
  focus: "2px"
spacing:
  compact: "8px"
  text: "12px"
  inset: "18px"
  medium: "20px"
  mobile-gutter: "22px"
  section: "34px"
  column: "48px"
components:
  status:
    backgroundColor: "{colors.tint}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "22px 28px"
  reply:
    backgroundColor: "{colors.reply-surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "10px 14px"
  reply-improved:
    backgroundColor: "{colors.comparison-improved}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "10px 14px"
  code:
    backgroundColor: "{colors.code-surface}"
    rounded: "{rounded.surface}"
    padding: "3px 7px"
  pending-panel:
    backgroundColor: "{colors.tint}"
    rounded: "{rounded.surface}"
    padding: "24px 28px"
---

# Design System: 待辦小幫手

## Overview

**Creative North Star:「可核對的閱讀紀錄」** — a descriptive name for the implemented direction, not an additional user-approved slogan.

This is a Read-mode visual system for Traditional Chinese content. White space, dark ink and restrained green distinguish headings, evidence and supporting notes. Its hierarchy helps a reader understand a change and inspect the underlying results without ornamental distractions.

The user approved B「前後對照」for the development-record surface. The comparison composition belongs to that surface; its readable type, flat surfaces and restrained accent are the reusable system. The source of truth is `docs/styles.css` and `docs/index.html`, with the approved direction recorded in `.impeccable/surfaces/development-record.md`.

**Key Characteristics:**
- System Chinese typography with selectable text.
- Flat, lightly tinted evidence regions and fine dividers.
- Explicit written status alongside color.

Documentation is extracted from the implemented source. The primary fresh reviewer passed after a mobile caption fix, as reported by the coordinating agent. The CLI launcher was unavailable; no CLI quantitative checks or automated visual validation are claimed here.

## Colors

A single forest-green accent sits within white and green-tinted neutrals. Frontmatter values are normative.

### Primary
- **Forest green** (`primary`): section headings, brand, links and passed-result labels.
- **Deep green** (`primary-hover`): hovered links.
- **Focus green** (`focus`): keyboard outlines.

### Neutral
- **Reading white** (`surface`): page and navigation background.
- **Dark ink** (`ink`): body content and pending status.
- **Quiet green tint** (`tint`): status, logs and pending-test containers.
- **Muted green-gray** (`muted`): metadata, captions and supporting notes.
- **Fine green-gray line** (`line`): dividers and evidence-table borders.
- Comparison, reply, code and footer surfaces use the named contextual neutrals in frontmatter; the improved comparison uses the stronger pale-green tone.

**The Written Status Rule.** State “本機” and “待完成” in text; green alone must never imply that all testing is complete.

## Typography

**Display and Body Font:** the Traditional Chinese system stack in frontmatter. No web font is required. Inline code retains the body family; command blocks and raw logs use the separate system monospace stack.

### Hierarchy
- **Display:** page title; sizes reduce to (36px) at the tablet breakpoint and (32px, line-height 1.35) on mobile.
- **Headline:** section headings, reducing to (25px) on mobile.
- **Title:** subheadings, reducing to (19px) on mobile; comparison headings use (21px) on desktop.
- **Body:** ordinary reading text with a maximum paragraph measure (74ch).
- **Intro:** a distinct lead (20px, line-height 1.7), reducing to (17px) on mobile.
- **Label:** metadata and captions; evidence-table text is (14px, line-height 1.7), with passed labels (12px, weight 600).
- **Log:** command blocks use the frontmatter role; raw test output reduces to (12px).

**The Reading Measure Rule.** Keep prose constrained while allowing comparisons and evidence to span the content area.

## Layout

The main content is centered with a maximum outer width (1440px), desktop padding (42px 4.17vw 84px). The sticky masthead has minimum height (64px), padding (14px max(4.17vw,24px)). Desktop opening columns are `minmax(0,1.8fr) minmax(300px,1fr)` with a (50px) gap. Paired explanatory articles use equal columns with a (48px) gap and a fine center divider; the second article has (40px) left padding.

The approved desktop comparison is two equal columns inside one framed region. Each column pairs labels and replies using (105px 1fr), with gaps (18px 20px) and margins (22px 24px 0). The full-width evidence table has fixed layout, a (24%) first column, and three input/expected/actual columns. Evidence notes use (1.15fr 1fr), gap (56px). Later reading sections use top margin (64px), top padding (30px) and a divider.

Exact responsive rules:
- At **min-width (1500px)**, main horizontal padding becomes (60px); masthead and footer gutters become `max(60px,calc((100vw - 1320px)/2))`.
- At **max-width (1000px)**, the opening becomes (1.5fr 1fr), gap (28px); navigation gap becomes (20px). Comparison labels and replies stack into one column with gap (8px), margins (16px 20px 0).
- At **max-width (760px)**, main padding becomes (28px 22px 56px); the masthead stacks and its navigation scrolls horizontally. Opening, paired articles, comparison and evidence notes stack. Comparison label/reply rows return to (88px 1fr), gap (14px 12px), margins (18px); the center divider becomes a horizontal divider. Table headers hide, rows become blocks, and each cell exposes its written `data-label`. **Table and caption both display as blocks at width (100%)**, preserving the full-width caption above all results. Archive links change from two columns to one; footer stacks.

Desktop scroll padding and section offsets are (95px); mobile scroll padding is (120px) and section scroll margin is (125px). Printing removes sticky positioning and navigation, reduces main padding to (22px), hides expandable raw logs and keeps evidence regions together where possible.

## Elevation & Depth

There are no shadows. Tonal backgrounds, one-pixel borders and the comparison’s two-pixel green top edge provide structure. The masthead’s stacking level supports sticky navigation without adding visual elevation. Links transition color and background over (.18s ease-out); reduced-motion preferences disable link transitions and smooth scrolling.

## Shapes

Surfaces and inline code have gently squared corners using the surface radius. The comparison rounds only its lower corners. Dividers stay straight. Keyboard focus has a (3px) outline, offset (5px), and the smaller focus radius. No pill or circular card language is implemented.

## Components

### Navigation and links

Compact textual navigation uses (14px, weight 550), with a (25px, weight 750) brand. Links are green; hover deepens the color and thickens the underline to (2px). Navigation links add an underline on hover. Keyboard focus uses the visible outline described in Shapes. Mobile navigation remains a single horizontally scrollable row (13px), under a (22px) brand. The skip link becomes visible when focused.

### Status and pending-test containers

Flat tint panels use the surface radius. The headline passed status is green (20px, line-height 1.6); pending status is dark ink (18px). Mobile headline and pending text reduce to (18px) and (16px). Status padding becomes (20px) at tablet size, then (18px 20px) on mobile. The larger pending-test container reduces to (20px) mobile padding. These are informational regions, with no interactive hover or selected state.

### Comparison and reply regions

The first-version and improved-version columns share a label/reply grammar; the improved heading and replies use the stronger pale-green surface. Replies preserve newlines and wrap long content anywhere. Their mobile padding becomes (9px 11px), with (14px) text. The comparison is a reusable evidence pattern, not a chat-client screenshot.

### Evidence table

Desktop cells have (15px 18px) padding and fine borders. Mobile cells use (7px 0), rows use (14px 0), and textual labels precede each value (12px, weight 500). The caption remains full-width. Passed status remains attached to the actual result and explicitly says “通過 · 本機”.

### Code and disclosure

Inline code is gently rounded and uses the reading family. Monospaced logs use tinted containers with (18px) padding and horizontal overflow handling; the raw log wraps and has maximum height (560px). The disclosure summary is green (weight 600), with (13px 0) padding, a pointer cursor and keyboard outline. Its native expanded/collapsed behavior is retained.

## Do's and Don'ts

### Do:
- **Do** preserve the Chinese reading hierarchy, written status and source notes.
- **Do** retain the desktop comparison and stacked mobile behavior for this approved surface.
- **Do** keep the mobile table caption full-width and labels adjacent to their results.
- **Do** use existing tint, border and corner treatments for related evidence regions.

### Don't:
- **Don't** portray local results or mock layouts as LINE真人測試 evidence.
- **Don't** replace the flat reading system with decorative shadows, oversized pills or new typefaces without a new design decision.
- **Don't** turn the approved page composition into a universal layout requirement for unrelated surfaces.
- **Don't** claim quantitative visual validation that was not run.
