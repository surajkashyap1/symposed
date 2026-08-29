"use client";

import { useId } from "react";

// The Symposed mark: an open book with the brand "S" set into the gutter —
// the book parts around the letter (an SVG mask cuts a channel, so the
// interlock survives any background). The S is the true Newsreader glyph
// outline, extracted from the shipped font subset (scripts/extract-glyph.mjs);
// the book is the canonical open-book silhouette (lucide `book-open`, ISC).
// Colour comes from `currentColor`.

export const S_PATH =
  "M40.1 18.7L40.1 18.7L36.8 17.9L39.4 16.0L40.2 16.0L41.3 26.1L39.9 26.2L36.4 19.4L37.3 20.5Q36.1 19.6 34.8 19.3Q33.6 18.9 32.1 18.9L32.1 18.9Q29.2 18.9 27.5 20.2Q25.9 21.5 25.9 23.9L25.9 23.9Q25.9 25.4 26.5 26.4Q27.1 27.4 28.2 28.1Q29.3 28.8 30.7 29.3Q32.1 29.8 33.6 30.3L33.6 30.3Q35.1 30.8 36.7 31.4Q38.2 32.0 39.5 32.9Q40.7 33.9 41.5 35.3Q42.3 36.8 42.3 39.0L42.3 39.0Q42.3 42.0 40.9 44.0Q39.5 46.0 37.0 47.0Q34.5 48.0 31.2 48.0L31.2 48.0Q28.9 48.0 27.2 47.7Q25.5 47.4 23.6 46.7L23.6 46.7L21.7 38.7L23.4 38.7L28.4 46.7L24.5 44.1Q26.3 45.0 27.8 45.4Q29.2 45.9 30.9 45.9L30.9 45.9Q33.4 45.9 35.2 45.3Q37.0 44.6 38.0 43.4Q38.9 42.1 38.9 40.1L38.9 40.1Q38.9 38.4 38.1 37.3Q37.4 36.1 36.1 35.4Q34.8 34.7 33.3 34.2Q31.7 33.6 30.2 33.1L30.2 33.1Q28.7 32.6 27.4 31.9Q26.0 31.3 25.0 30.4Q23.9 29.5 23.3 28.2Q22.7 26.9 22.7 25.0L22.7 25.0Q22.7 22.4 23.9 20.6Q25.1 18.8 27.4 17.8Q29.6 16.9 32.7 16.9L32.7 16.9Q34.7 16.9 36.5 17.3Q38.3 17.8 40.1 18.7";

export const BOOK_LEFT = "M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z";
export const BOOK_RIGHT = "M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h6z";

// Tuned proportions (viewBox 0 0 96 64): book scaled 3.3x and centred,
// S at 1.0 in the gutter, channel dilation 3.5. Weights are deliberately
// heavy — the mark is a solid, filled form, not line art.
const BOOK_T = "translate(8.4 -6.6) scale(3.3)";
const S_T = "translate(16 -0.6) scale(1)";
const BOOK_STROKE = 2.4;
const S_STROKE = 1.15;
const MASK_DILATE = 3.8;

export function LogoMark({
  height = 24,
  className,
}: {
  height?: number;
  className?: string;
}) {
  const id = useId();
  return (
    <svg
      width={(height * 96) / 64}
      height={height}
      viewBox="0 0 96 64"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
      className={className}
    >
      <defs>
        <mask id={id}>
          <rect width="96" height="64" fill="white" />
          <g transform={S_T}>
            <path d={S_PATH} fill="black" stroke="black" strokeWidth={MASK_DILATE} />
          </g>
        </mask>
      </defs>
      <g
        transform={BOOK_T}
        stroke="currentColor"
        strokeWidth={BOOK_STROKE}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        mask={`url(#${id})`}
      >
        <path d={BOOK_LEFT} />
        <path d={BOOK_RIGHT} />
      </g>
      <g transform={S_T}>
        <path
          d={S_PATH}
          fill="currentColor"
          stroke="currentColor"
          strokeWidth={S_STROKE}
        />
      </g>
    </svg>
  );
}

// The favicon composition as an inline component: paper mark on a claret
// tile. Reads far crisper at header sizes than the bare mark on paper, and
// matches the browser-tab / app icon so the brand is one mark everywhere.
// Brand constants (not theme tokens) so it never flips with dark mode.
export function LogoTile({
  size = 28,
  className,
}: {
  size?: number;
  className?: string;
}) {
  const id = useId();
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
      className={className}
    >
      <defs>
        <mask id={id}>
          <rect width="64" height="64" fill="white" />
          <g transform="translate(11.52 6.28) scale(0.64)">
            <path d={S_PATH} fill="black" stroke="black" strokeWidth={3.8} />
          </g>
        </mask>
      </defs>
      <rect width="64" height="64" rx="14" fill="var(--color-brand)" />
      <g
        transform="translate(5.6 5.24) scale(2.2)"
        stroke="var(--color-brand-foreground)"
        strokeWidth={2.4}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        mask={`url(#${id})`}
      >
        <path d={BOOK_LEFT} />
        <path d={BOOK_RIGHT} />
      </g>
      <g transform="translate(11.52 6.28) scale(0.64)">
        <path
          d={S_PATH}
          fill="var(--color-brand-foreground)"
          stroke="var(--color-brand-foreground)"
          strokeWidth={1.15}
        />
      </g>
    </svg>
  );
}

export function LogoLockup({
  markHeight = 26,
  textClassName = "text-xl",
  tone = "default",
}: {
  markHeight?: number;
  textClassName?: string;
  /** "oncolor" renders the whole lockup in cream, for claret surfaces. */
  tone?: "default" | "oncolor";
}) {
  const wordClass =
    tone === "oncolor" ? "text-brand-foreground" : "text-foreground";
  return (
    <span className="inline-flex items-center gap-2">
      {tone === "oncolor" ? (
        <LogoMark height={markHeight} className="text-brand-foreground" />
      ) : (
        <LogoTile size={markHeight + 2} />
      )}
      <span
        className={`font-heading font-semibold tracking-tight ${wordClass} ${textClassName}`}
      >
        Symposed
      </span>
    </span>
  );
}
