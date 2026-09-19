"use client";

import { useEffect } from "react";

// Fires a single first-touch visit per browser (spec §9.2). Deduped
// client-side via localStorage so a returning visitor is not counted twice; the
// server also dedupes with a cookie as a backstop. The POST carries no body:
// the visit's channel is read server-side from the first-touch cookie.
export function AttributionBeacon() {
  useEffect(() => {
    try {
      if (localStorage.getItem("sym_visited")) return;
    } catch {
      // Private mode or blocked storage: fall back to the server-side cookie
      // dedupe rather than skipping the visit entirely.
    }
    // Mark visited only once the POST is accepted, so a dropped first request
    // (offline, blocked, 500) retries on the next load instead of being lost.
    void fetch("/api/attribution/visit", { method: "POST", keepalive: true })
      .then(() => {
        try {
          localStorage.setItem("sym_visited", "1");
        } catch {
          /* storage blocked: the server cookie already deduped this visit */
        }
      })
      .catch(() => {});
  }, []);

  return null;
}
