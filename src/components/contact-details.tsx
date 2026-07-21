// Shown to both parties once an application is accepted (auto-reveal). Contact
// details are never rendered anywhere else — see the Contact Sharing Policy.
export function ContactDetails({
  heading,
  email,
  phone,
}: {
  heading: string;
  email: string;
  phone: string | null;
}) {
  return (
    <div className="rounded-md border border-success/30 bg-success/5 px-4 py-3 text-sm">
      <p className="font-medium text-success-foreground">{heading}</p>
      <dl className="mt-2 flex flex-col gap-1">
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 text-xs text-muted-foreground">Email</dt>
          <dd>
            <a href={`mailto:${email}`} className="text-primary hover:underline">
              {email}
            </a>
          </dd>
        </div>
        {phone && (
          <div className="flex gap-2">
            <dt className="w-14 shrink-0 text-xs text-muted-foreground">Phone</dt>
            <dd>
              <a href={`tel:${phone.replace(/\s+/g, "")}`} className="text-primary hover:underline">
                {phone}
              </a>
            </dd>
          </div>
        )}
      </dl>
      <p className="mt-2 text-xs text-muted-foreground">
        Please use these details only for this collaboration.
      </p>
    </div>
  );
}
