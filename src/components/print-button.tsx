"use client";

import { Button } from "@/components/ui/button";

// Amendment §8.3 — the record is exportable as a PDF. With no PDF dependency
// (zero-budget), the reliable route is the browser's own "Save as PDF" via
// print; this button opens that dialog and the page carries print styles.
export function PrintButton({ label = "Download as PDF" }: { label?: string }) {
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      onClick={() => window.print()}
      className="print:hidden"
    >
      {label}
    </Button>
  );
}
