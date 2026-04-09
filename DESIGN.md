# Design System — UIT AI Document Query System

## Product Context

- **What this is:** An AI-powered document query system that answers questions about Ho Chi Minh City University of Information Technology policies and regulations, with temporal awareness of document validity, amendments, and expiration.
- **Who it's for:** UIT students (primary), faculty, and administrators. Secondary: thesis committee for evaluation.
- **Space/industry:** Vietnamese university AI, academic document management, institutional knowledge systems.
- **Project type:** Full-stack web app — student-facing query interface + admin management dashboard.

## Aesthetic Direction

- **Direction:** "A government archive that learned to think"
- **Decoration level:** Intentional — warmth and authority markers, no decorative elements
- **Mood:** Serious, trustworthy, precise — but visibly modern and intelligent. When a faculty member sees this on a screen, before reading a word, it should feel like it belongs to the university — not like another SaaS subscription.
- **Reference products:** Perplexity (citations as first-class UI), Vietnamese government document aesthetic (official seal red, document number hierarchy)

## Typography

- **Display/Hero:** Fraunces (variable optical serif, `font-variation-settings: 'opsz' [size]`) — page headings, query display, empty states. Used sparingly. Signals institutional authority without coldness.
- **Body/UI:** Be Vietnam Pro — designed for Vietnamese readability, handles tone marks and diacritics correctly at 13-15px. Every Vietnamese user will feel the difference vs. Inter/Outfit.
- **Data/Mono:** IBM Plex Mono — ALL document numbers, dates, confidence values, amendment references, temporal delta badges. Creates a clear visual register separating "system output" from "human text."
- **Loading:** Google Fonts CDN
  ```
  https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..900;1,9..144,300..900&family=Be+Vietnam+Pro:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=IBM+Plex+Mono:wght@400;500;600&display=swap
  ```
- **Scale:**
  - display: 48px / Fraunces 700 / lh 1.1
  - heading-lg: 28px / Fraunces 600 / lh 1.2
  - heading-md: 22px / Fraunces 600 / lh 1.25
  - heading-sm: 17px / Fraunces 700 / lh 1.3
  - body: 15px / Be Vietnam Pro 400 / lh 1.65
  - body-sm: 14px / Be Vietnam Pro 400 / lh 1.6
  - ui: 13px / Be Vietnam Pro 500-600 / lh 1.4
  - label: 10px / IBM Plex Mono 500 / UPPERCASE / letter-spacing 0.1em
  - mono: 11-13px / IBM Plex Mono 400-600 / lh 1.5

## Color

- **Approach:** Restrained — the palette is purpose-driven, every color earns its place

### Light Mode
```css
--bg:           #FAF8F5;   /* warm paper — the product feels grounded in physical documents */
--bg-elevated:  #FFFEFB;   /* cards, panels */
--bg-recessed:  #F0EDE8;   /* inputs, alternating rows, code blocks */
--border:       #D6D0C7;   /* all borders */
--text-primary: #1A1714;   /* warm near-black */
--text-secondary:#6B6560;  /* secondary labels */
--text-tertiary:#9E9890;   /* placeholders, captions */
```

### Dark Mode
```css
--bg:           #1A1714;
--bg-elevated:  #242018;
--bg-recessed:  #141210;
--border:       #2E2A26;
--text-primary: #F5F2EE;
--text-secondary:#A09990;
--text-tertiary:#6B6560;
```

### Brand
```css
--vermillion:       #C1381F;   /* primary — the red of the Vietnamese official seal */
--vermillion-light: #F5E5E1;   /* tints for active states in light mode */
--vermillion-dark:  #8B2510;   /* hover, press states */
```

### Temporal State Colors (critical — used in Authority Rail, badges, table rows)
```css
--valid:         #1F7A4B;   /* active / current documents — forest green */
--valid-bg:      #EBF7F1;   /* badge backgrounds */
--expiring:      #A85B00;   /* expiring within 30 days — amber */
--expiring-bg:   #FEF3E2;
--superseded:    #6B6560;   /* replaced documents — muted, visually demoted */
--superseded-bg: #F0EDE8;
--amended:       #5C4A8A;   /* documents that amend others — muted violet */
--amended-bg:    #F0ECF8;
```

### Accent
```css
--link: #0F5C4A;   /* citation anchors, hyperlinks — deep teal */
```

## Spacing

- **Base unit:** 8px
- **Density:** Comfortable — not cramped data-table, not airy marketing
- **Scale:** 2 4 8 12 16 20 24 32 40 48 64

## Layout

### Student Query Interface (primary surface)
**No left sidebar.** Centered content area + permanent right Authority Rail.

```
┌─────────────────────────────────────────────────────┐
│  UIT AI                              09/04/2026      │  ← 48px top strip
├────────────────────────────┬────────────────────────┤
│                            │                        │
│  Centered query + answer   │   Authority Rail       │
│  max-width: 720px          │   width: 320px         │
│  padding: 40px             │                        │
│                            │   Document cards with: │
│  Query shown as Fraunces   │   · 3px validity bar   │
│  heading (not chat bubble) │   · doc number (mono)  │
│                            │   · temporal delta     │
│  Answer as typographic     │   · amendment chain    │
│  document — paragraphs,    │                        │
│  inline [citation] anchors │                        │
│                            │                        │
└────────────────────────────┴────────────────────────┘
```

**Top strip:** 48px. UIT AI wordmark (Fraunces) left, current date (IBM Plex Mono) right. No user avatar cluster, no breadcrumbs, no hamburger. The date is structural — document validity is relative to today.

### Admin Dashboard
Minimal left sidebar (220px) + main content area. Same visual language.

- Sidebar: brand wordmark, flat nav items with vermillion active state (3px left indicator)
- Main: Fraunces page headings, stat cards with Fraunces numerals, document tables with temporal badges
- No top topbar clutter — just page title + primary action button

### Grid
- Desktop: sidebar 220px | content flexible | rail 320px
- Max content width: 720px (query interface), flexible (admin)
- Breakpoints: 768px (mobile collapses Authority Rail to bottom sheet), 1024px (full layout)

### Border Radius
```css
--radius-sm:   4px;    /* data badges, mono pills, table cells */
--radius-md:   8px;    /* cards, inputs, buttons */
--radius-lg:   12px;   /* panels, doc cards, stat cards */
--radius-full: 9999px; /* badge dots, avatar circles */
```

## Motion

- **Approach:** Minimal-functional
- **Easing:** enter(ease-out) exit(ease-in) move(ease-in-out)
- **Duration:** micro 80ms | short 150ms | medium 200ms
- **Specifics:**
  - Validity bars fade in on first render (opacity 0 → 1, 200ms ease-out)
  - Citation hover reveals micro-tooltip (150ms)
  - Superseded doc cards fade to opacity 0.65
  - No bounce, no particle effects, no scroll-driven animations

## Key UI Patterns

### Authority Rail — Document Card
Each cited document gets a card with four visual layers:
1. **3px validity bar** at top of card — color encodes temporal state at a glance, no text needed
2. **Document number** as card headline in IBM Plex Mono 12px 500 — e.g., `108/QĐ-ĐHCNTT`
3. **Temporal delta badge** — `Valid 3yr 2mo` or `Expired 14 days ago` (never a raw percentage)
4. **Amendment chain** — if superseded, dashed border + mono label linking to current version; superseded cards show at 65% opacity

### Citation Anchors (in answer text)
```css
/* Inline citation — renders as [QĐ 108] */
font-family: var(--font-mono);
font-size: 11px;
color: var(--link);
background: rgba(15, 92, 74, 0.08);
padding: 1px 4px;
border-radius: 3px;
```

### Confidence Display
**Never show raw percentage numbers.** Instead:
- High confidence: standard answer styling (no special treatment)
- Medium confidence: subtle amber left-border on answer block
- Low confidence: amber left-border + mono caption "Thông tin có thể không đầy đủ — kiểm tra tài liệu gốc"
- After answer: `"Dựa trên N tài liệu chính thức từ năm YYYY"` (IBM Plex Mono, muted)

### No Chat Bubbles
Queries display as a Fraunces heading above the answer area. Answers flow as typographic documents — paragraphs, inline citations, structured sections. The interface is not a chatbot. The form communicates the gravity of official sources.

## Anti-patterns (never use in this codebase)

- Purple or violet gradients anywhere
- Outfit or Inter as primary font (already in `web_implement` — replace)
- Electric blue `#465fff` as primary (already in `web_implement` — replace)
- Chat bubble metaphor (alternating user/bot bubbles)
- "Confidence: 87%" as raw percentage display
- Generic 3-column icon grid feature sections
- Glassmorphism, gradient borders, floating orbs
- Bubbly uniform border-radius (e.g., `rounded-xl` on everything)
- Tailwind default slate grays as surfaces (cold, not warm)

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-09 | Fraunces as display font | Genuine personality without screaming "startup". Institutional without being cold. |
| 2026-04-09 | Be Vietnam Pro as body font | Designed for Vietnamese readability. Handles tone marks + diacritics better than Inter/Outfit at 13-14px. |
| 2026-04-09 | IBM Plex Mono for all data | Creates clear visual register between "system output" (document numbers, dates) and "human text." |
| 2026-04-09 | Vermillion #C1381F as primary | Color of Vietnamese official seals. Signals authority without danger. Unused in AI product space. |
| 2026-04-09 | Warm paper #FAF8F5 background | Grounds product in physical document aesthetic. Differentiates from generic cold-slate SaaS. |
| 2026-04-09 | No left sidebar on query interface | Authority Rail on right is the innovation. Documents are as important as the answer. |
| 2026-04-09 | No chat bubbles | Form communicates gravity of official sources. Generated institutional reports, not casual conversation. |
| 2026-04-09 | Temporal states as 4 distinct colors | Valid / Expiring / Superseded / Amended are semantically distinct — each needs its own color signal. |
| 2026-04-09 | Document number as card headline | Vietnamese academics/admins recognize document numbers as primary identity. Mono makes them scannable. |
| 2026-04-09 | Design system created | Created by /design-consultation based on competitive research (Perplexity, ChatPDF, Vietnamese EdTech landscape) + Claude subagent direction |
