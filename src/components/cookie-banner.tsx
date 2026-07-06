"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

const STORAGE_KEY = "symposed.cookie-consent";

// We currently set only essential cookies (authentication). This is an
// informational notice with acknowledgement, stored locally so it shows once.
export function CookieBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      // Client-only consent check on mount (avoids an SSR hydration mismatch).
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (!localStorage.getItem(STORAGE_KEY)) setShow(true);
    } catch {
      /* localStorage unavailable — skip the banner */
    }
  }, []);

  if (!show) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(STORAGE_KEY, new Date().toISOString());
    } catch {
      /* ignore */
    }
    setShow(false);
  };

  return (
    <div
      role="region"
      aria-label="Cookie notice"
      className="fixed inset-x-0 bottom-0 z-50 border-t bg-background/95 backdrop-blur"
    >
      <div className="mx-auto flex w-full max-w-5xl flex-col items-start justify-between gap-3 px-6 py-4 sm:flex-row sm:items-center">
        <p className="text-sm text-muted-foreground">
          We use only essential cookies to keep you signed in. See our{" "}
          <Link href="/privacy" className="text-foreground underline">
            Privacy Policy
          </Link>
          .
        </p>
        <Button size="sm" onClick={dismiss} className="shrink-0">
          Got it
        </Button>
      </div>
    </div>
  );
}
