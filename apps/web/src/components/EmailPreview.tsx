import { Mail } from "lucide-react";

/**
 * Renders user-entered text as plain text nodes only (React escapes it), so
 * markup or scripts in a subject or body can never execute.
 */
export function EmailPreview({ subject, body, audience }: { subject: string; body: string; audience?: string }) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <div className="flex items-center gap-2 border-b bg-muted/50 px-4 py-2.5 text-xs font-medium text-muted-foreground">
        <Mail className="h-3.5 w-3.5" aria-hidden />
        Email preview
      </div>
      <dl className="space-y-1 border-b px-4 py-3 text-[13px]">
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 text-muted-foreground">From</dt>
          <dd className="font-medium">Pulse Team &lt;hello@pulse.example&gt;</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 text-muted-foreground">To</dt>
          <dd>{audience ?? "Recipient"}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-14 shrink-0 text-muted-foreground">Subject</dt>
          <dd className="break-words font-semibold">{subject || <span className="font-normal italic text-muted-foreground">No subject yet</span>}</dd>
        </div>
      </dl>
      <div className="max-h-[420px] overflow-y-auto whitespace-pre-wrap break-words px-4 py-4 text-sm leading-relaxed text-slate-700">
        {body || <span className="italic text-muted-foreground">Your message will appear here.</span>}
      </div>
    </div>
  );
}
