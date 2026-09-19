"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

// Copies a generated referral link so it can be sent (spec §9.3). Falls back to
// selecting nothing gracefully if the clipboard API is unavailable.
export function CopyLinkButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // Clipboard blocked: leave the visible link for manual copy.
        }
      }}
    >
      {copied ? "Copied" : "Copy link"}
    </Button>
  );
}
