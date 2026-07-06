import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { SubmitButton } from "@/components/submit-button";
import { Textarea } from "@/components/ui/textarea";
import {
  PROJECT_TYPES,
  EXPERIENCE_LEVELS,
  ROLE_CATEGORIES,
  type Project,
} from "@/lib/project-meta";

export function ProjectForm({
  action,
  project,
  error,
  submitLabel,
}: {
  action: (formData: FormData) => void;
  project?: Project | null;
  error?: string;
  submitLabel: string;
}) {
  return (
    <form action={action} className="flex flex-col gap-5">
      {project && <input type="hidden" name="id" value={project.id} />}

      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
        <strong>Listings are public — no personal or patient data.</strong> Do
        not include patient-identifiable information (names, NHS numbers, dates
        of birth, case details), phone numbers, email addresses, or confidential
        NHS/university information. Contact details are exchanged privately
        after you accept an applicant. See our{" "}
        <a href="/acceptable-use" className="underline" target="_blank">
          Acceptable Use Policy
        </a>{" "}
        and{" "}
        <a href="/contact-sharing" className="underline" target="_blank">
          Contact Sharing Policy
        </a>
        .
      </div>

      <div className="grid gap-2">
        <Label htmlFor="title">Project title</Label>
        <Input
          id="title"
          name="title"
          required
          placeholder="e.g. Retrospective audit of A&E waiting times"
          defaultValue={project?.title ?? ""}
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="description">Description</Label>
        <Textarea
          id="description"
          name="description"
          required
          rows={6}
          placeholder="What is the project, what will collaborators do, expected outputs and timeline?"
          defaultValue={project?.description ?? ""}
        />
      </div>

      <div className="grid gap-5 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="projectType">Type</Label>
          <Select
            id="projectType"
            name="projectType"
            defaultValue={project?.projectType ?? "audit"}
            options={PROJECT_TYPES}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="experienceLevel">Experience level</Label>
          <Select
            id="experienceLevel"
            name="experienceLevel"
            defaultValue={project?.experienceLevel ?? "beginner_welcome"}
            options={EXPERIENCE_LEVELS}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="specialty">Specialty</Label>
          <Input
            id="specialty"
            name="specialty"
            placeholder="e.g. Cardiology"
            defaultValue={project?.specialty ?? ""}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="roleCategory">Entry-level role (optional)</Label>
          <Select
            id="roleCategory"
            name="roleCategory"
            defaultValue={project?.roleCategory ?? ""}
            options={[
              { value: "", label: "None" },
              ...ROLE_CATEGORIES.map((r) => ({ value: r, label: r })),
            ]}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="positionsAvailable">Positions available</Label>
          <Input
            id="positionsAvailable"
            name="positionsAvailable"
            type="number"
            min={1}
            defaultValue={project?.positionsAvailable ?? 1}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="applicationDeadline">Application deadline (optional)</Label>
          <Input
            id="applicationDeadline"
            name="applicationDeadline"
            type="date"
            defaultValue={project?.applicationDeadline ?? ""}
          />
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          name="isBeginnerFriendly"
          defaultChecked={project?.isBeginnerFriendly ?? false}
          className="size-4 rounded border-input accent-primary"
        />
        Mark as beginner-friendly (gets higher visibility)
      </label>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          name="isSupervisor"
          defaultChecked={!!project?.supervisorId}
          className="mt-0.5 size-4 rounded border-input accent-primary"
        />
        <span>
          I am the supervisor for this project
          <span className="block text-xs text-muted-foreground">
            Leave unticked if you&apos;re posting on behalf of a team or aren&apos;t
            the named supervisor.
          </span>
        </span>
      </label>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          name="noConfidentialInfo"
          required
          className="mt-0.5 size-4 rounded border-input accent-primary"
        />
        <span>
          I confirm this listing contains no patient-identifiable or
          confidential information and complies with the{" "}
          <a href="/acceptable-use" className="underline" target="_blank">
            Acceptable Use Policy
          </a>{" "}
          and{" "}
          <a href="/privacy" className="underline" target="_blank">
            Privacy Notice
          </a>
          .
        </span>
      </label>

      <SubmitButton className="self-start" pendingLabel="Saving...">
        {submitLabel}
      </SubmitButton>
    </form>
  );
}
