# Design

Visual system for Symposed. Direction: **Scholarly Editorial** — academic-
publishing heritage executed as a modern product UI. Type and whitespace lead;
claret is the single restrained accent. Tokens live in `src/app/globals.css`
(OKLCH); fonts wired in `src/app/layout.tsx` via `next/font`.

## Theme

Warm off-white "paper" surface with near-black ink, a deep **claret/oxblood**
primary, and a **deep teal-green** success/positive role. Crisp (not soft):
small radius, hairline warm borders, minimal shadow. Cards recede — separation
comes from borders and space, not elevation. Light and dark are both branded;
dark is a deep ink-green, not neutral grey.

## Color (light)

| Role | OKLCH | Hex | Use |
|---|---|---|---|
| background | `oklch(0.985 0.004 91.4)` | `#FBFAF7` | page "paper" (true off-white, not cream) |
| foreground (ink) | `oklch(0.273 0.021 216.1)` | `#1B2A2E` | body + headings |
| card / popover | `oklch(1 0 0)` | `#FFFFFF` | surfaces (lift via border, not luminance) |
| primary (claret) | `oklch(0.410 0.107 23.0)` | `#7A2E2E` | buttons, links, focus ring, brand mark |
| primary-foreground | `oklch(0.971 0.010 58.2)` | `#FBF4EF` | text on claret |
| secondary / muted | `oklch(0.947 0.013 86.8)` | `#F1EDE4` | warm paper-grey fill |
| muted-foreground | `oklch(0.459 0.016 82.4)` | `#5C574E` | secondary text (6.9:1) |
| accent | `oklch(0.929 0.016 86.4)` | `#ECE7DC` | hover surface |
| border | `oklch(0.905 0.017 84.6)` | `#E5DFD3` | hairline |
| input | `oklch(0.872 0.020 84.6)` | `#DBD4C6` | field edges |
| success (teal-green) | `oklch(0.489 0.082 184.8)` | `#0F6F66` | verified, beginner-friendly, positive |

Dark mirrors with a deep ink-green bg (`#16201F`), warm off-white ink
(`#ECE6DB`), lightened claret (`#C76A5F`) and teal-green (`#4FB3A6`). Charts:
claret → teal-green → ochre → ink → light-claret. Destructive stays a vivid red,
deliberately distinct from the darker, muted claret primary.

## Typography

Contrast-axis pairing (serif display + humanist sans), replacing Geist (a slop
tell).

- **Headings:** **Newsreader** (editorial reading serif, conventional
  letterforms) — `var(--font-serif)` / `--font-heading`. Applied to real
  `h1–h4` and the brand mark **only**. Never on buttons, labels, inputs, or data
  (product-register ban on display fonts in UI controls). Heading ligatures are
  disabled (`font-variant-ligatures: none`) for clean letterforms.
- **Body / UI:** **Hanken Grotesk** (humanist sans) — `var(--font-sans)`.
  Carries body, buttons, labels, tables, everything functional.
- Fixed rem scale (not fluid clamp); tight-ish scale ratio; prose capped 65–75ch.

## Components

shadcn/ui (Radix), Tailwind v4. Conventions: hairline `border` + small radius
(`--radius: 0.375rem`); one claret primary button shape reused everywhere;
native `<select>` in server-action forms; full default/hover/focus/disabled
states. Beginner-friendly + verified use the `success` token, not raw emerald.

## Motion

Restrained, state-only: 150–250ms, ease-out. No page-load choreography (product
loads into a task). Every transition has a `prefers-reduced-motion` fallback.

## Logo

The mark is an **open book with the brand "S" set into the gutter** — the
book parts around the letter via an SVG mask channel, so the interlock
survives any background. The S is the true Newsreader glyph outline
(extracted from the shipped font subset with `scripts/extract-glyph.mjs`);
the book is the canonical open-book silhouette (lucide `book-open`, ISC).
Canvas is wide (viewBox 0 0 96 64): book scaled 3.3× and centred, S at 1.0
in the gutter, mask dilation 3.8, book stroke 2.4 round-cap (S stroked 1.15 for weight). Geometry lives in
`src/components/logo.tsx` (`LogoMark`, colour via `currentColor`;
`LogoLockup` pairs it with "Symposed" in Newsreader 600). Favicon/app icon
(`src/app/icon.svg`, `src/app/apple-icon.png`) put the paper-coloured mark on
a claret tile (rx 14). Dark mode inherits the lightened claret via
`text-primary`. The homepage hero carries the mark as a 5%-opacity watermark.
