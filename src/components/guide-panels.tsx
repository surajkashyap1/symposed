"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { GuidePanel } from "@/lib/guides-meta";
import { cn } from "@/lib/utils";

// Amendment §5 — the three "What is included" panels, shown laterally.
// Systematic review is first and is the default view.
//
// Accessibility contract from the spec:
//  - swipe on touch, visible arrow controls on desktop, dot indicators;
//  - keyboard navigable with the left and right arrow keys, visible focus;
//  - ALL three panels present in the DOM and readable by screen readers. We
//    never use display:none to hide the inactive panels — they sit in a
//    horizontally scrollable, scroll-snapping track, so assistive tech reads
//    every one and touch users swipe between them natively.
export function GuidePanels({ panels }: { panels: readonly GuidePanel[] }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);

  const goTo = useCallback((i: number) => {
    const clamped = Math.max(0, Math.min(panels.length - 1, i));
    const track = trackRef.current;
    if (!track) return;
    const panel = track.children[clamped] as HTMLElement | undefined;
    panel?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
    setActive(clamped);
  }, [panels.length]);

  // Keep the dots + arrows in sync when the user swipes/scrolls directly.
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const i = Math.round(track.scrollLeft / track.clientWidth);
        setActive(Math.max(0, Math.min(panels.length - 1, i)));
      });
    };
    track.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      track.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(frame);
    };
  }, [panels.length]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      goTo(active + 1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      goTo(active - 1);
    }
  }

  return (
    <div
      role="group"
      aria-roledescription="carousel"
      aria-label="What is included, by review type"
      className="mt-6"
      onKeyDown={onKeyDown}
    >
      {/* Tabs: switch panel, and label the current position for screen readers */}
      <div role="tablist" aria-label="Review type" className="flex flex-wrap gap-2">
        {panels.map((p, i) => (
          <button
            key={p.key}
            type="button"
            role="tab"
            id={`guide-tab-${p.key}`}
            aria-selected={i === active}
            aria-controls={`guide-panel-${p.key}`}
            tabIndex={i === active ? 0 : -1}
            onClick={() => goTo(i)}
            className={cn(
              "rounded-full border px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              i === active
                ? "border-transparent bg-primary text-primary-foreground"
                : "bg-card text-muted-foreground hover:bg-secondary"
            )}
          >
            {p.title}
          </button>
        ))}
      </div>

      <div className="relative mt-4">
        {/* Scroll track: every panel stays in the DOM; scroll-snap + swipe */}
        <div
          ref={trackRef}
          className="flex snap-x snap-mandatory overflow-x-auto scroll-smooth rounded-lg border bg-card [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {panels.map((p) => (
            <section
              key={p.key}
              id={`guide-panel-${p.key}`}
              role="tabpanel"
              aria-labelledby={`guide-tab-${p.key}`}
              className="w-full shrink-0 snap-start p-6 sm:p-8"
            >
              <h3 className="font-heading text-lg font-semibold tracking-tight">
                {p.title}
              </h3>
              <ul className="mt-5 grid gap-x-10 gap-y-4 sm:grid-cols-2">
                {p.items.map(([lead, rest]) => (
                  <li key={lead} className="flex gap-2 text-sm leading-relaxed">
                    <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-primary/60" />
                    <span>
                      <strong className="font-semibold text-foreground">{lead}</strong>
                      {rest ? (
                        <span className="text-muted-foreground">, {rest}</span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>

        {/* Desktop arrow controls */}
        <button
          type="button"
          onClick={() => goTo(active - 1)}
          disabled={active === 0}
          aria-label="Previous review type"
          className="absolute left-2 top-1/2 hidden -translate-y-1/2 items-center justify-center rounded-full border bg-background/90 p-2 shadow-sm transition-opacity hover:bg-background disabled:pointer-events-none disabled:opacity-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:flex"
        >
          <ChevronLeft className="h-5 w-5" aria-hidden />
        </button>
        <button
          type="button"
          onClick={() => goTo(active + 1)}
          disabled={active === panels.length - 1}
          aria-label="Next review type"
          className="absolute right-2 top-1/2 hidden -translate-y-1/2 items-center justify-center rounded-full border bg-background/90 p-2 shadow-sm transition-opacity hover:bg-background disabled:pointer-events-none disabled:opacity-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:flex"
        >
          <ChevronRight className="h-5 w-5" aria-hidden />
        </button>
      </div>

      {/* Dot indicators */}
      <div className="mt-4 flex justify-center gap-2">
        {panels.map((p, i) => (
          <button
            key={p.key}
            type="button"
            onClick={() => goTo(i)}
            aria-label={`Show ${p.title}`}
            aria-current={i === active}
            className={cn(
              "h-2 rounded-full transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              i === active ? "w-6 bg-primary" : "w-2 bg-border hover:bg-primary/40"
            )}
          />
        ))}
      </div>
    </div>
  );
}
