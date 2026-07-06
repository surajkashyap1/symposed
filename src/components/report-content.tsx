import { Flag } from "lucide-react";
import { submitReport } from "@/app/reports/actions";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

// Collapsed report form for any content (Safety Policy §2). Renders nothing
// for signed-out visitors — reports need an account.
export function ReportContent({
  targetType,
  targetId,
  backTo,
  label = "Report",
}: {
  targetType: "project" | "question" | "profile" | "review";
  targetId: string;
  backTo: string;
  label?: string;
}) {
  return (
    <details className="group text-sm">
      <summary className="flex cursor-pointer list-none items-center gap-1 text-xs text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
        <Flag className="h-3 w-3" aria-hidden />
        {label}
      </summary>
      <form
        action={submitReport}
        className="mt-2 flex flex-col gap-2 rounded-md border bg-card p-3"
      >
        <input type="hidden" name="targetType" value={targetType} />
        <input type="hidden" name="targetId" value={targetId} />
        <input type="hidden" name="backTo" value={backTo} />
        <Textarea
          name="reason"
          rows={2}
          required
          maxLength={2000}
          placeholder="Why are you reporting this? (abuse, personal or patient data, spam, misleading…)"
        />
        <p className="text-xs text-muted-foreground">
          Reports are reviewed by the Symposed team. See our{" "}
          <a href="/safety" className="underline" target="_blank">
            Safety &amp; Reporting Policy
          </a>
          . For urgent safety issues email safety@symposed.org.
        </p>
        <Button type="submit" size="sm" variant="outline" className="self-start">
          Submit report
        </Button>
      </form>
    </details>
  );
}
