"use client";

import { useState } from "react";
import { DELIVERY_FORMATS } from "@/lib/teach-meta";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

// Live delivery is pre-selected deliberately (spec §4.1.4); choosing
// "recorded only" surfaces the evidence warning before submission.
export function TeachFormatField({
  defaultValue = "live_with_recordings",
}: {
  defaultValue?: string;
}) {
  const [value, setValue] = useState(defaultValue);

  return (
    <div className="grid gap-2">
      <Label htmlFor="deliveryFormat">Delivery format</Label>
      <Select
        id="deliveryFormat"
        name="deliveryFormat"
        required
        defaultValue={defaultValue}
        onValueChange={(v) => setValue(String(v))}
        options={DELIVERY_FORMATS.map((f) => ({
          value: f.value,
          label: f.label,
        }))}
      />
      {value === "recorded_only" && (
        <p className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          Some specialty criteria will not accept self-paced material without a
          live tutor. A recorded-only course may not count as teaching evidence
          for your application, a live series protects your evidence.
        </p>
      )}
    </div>
  );
}
