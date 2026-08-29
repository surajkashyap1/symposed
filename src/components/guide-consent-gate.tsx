"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

// The §3.2 consent block: two separate checkboxes, both unticked by default,
// both required before the payment button enables. Never pre-ticked, never
// combined — the first disapplies the 14-day cancellation right (Consumer
// Contracts Regulations 2013) and must be a real, active choice.
export function GuideConsentGate({ payLabel }: { payLabel: string }) {
  const [immediate, setImmediate] = useState(false);
  const [terms, setTerms] = useState(false);

  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-start gap-2.5 text-sm leading-relaxed">
        <input
          type="checkbox"
          name="consentImmediate"
          checked={immediate}
          onChange={(e) => setImmediate(e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-input accent-primary"
        />
        I request that Symposed begins work on my guide immediately, and I
        understand that I will lose my right to cancel this order once work has
        begun.
      </label>
      <label className="flex items-start gap-2.5 text-sm leading-relaxed">
        <input
          type="checkbox"
          name="consentTerms"
          checked={terms}
          onChange={(e) => setTerms(e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-input accent-primary"
        />
        <span>
          I have read and agree to the{" "}
          <a href="/terms" target="_blank" className="text-primary underline">
            Terms of Service
          </a>{" "}
          and the{" "}
          <a href="/privacy" target="_blank" className="text-primary underline">
            Privacy Policy
          </a>
          .
        </span>
      </label>
      <Button
        type="submit"
        size="lg"
        disabled={!immediate || !terms}
        className="mt-2 self-start"
      >
        {payLabel}
      </Button>
    </div>
  );
}
