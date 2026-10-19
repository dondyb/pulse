import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarClock, Info, Mail, Save, Send, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { EmailPreview } from "@/components/EmailPreview";
import { ErrorState, FieldError, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api, type CampaignPayload } from "@/lib/api";
import { TZ_LABEL, formatDateTime, jakartaInputToIso, toJakartaInput } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Audience } from "@/lib/types";

type Mode = "now" | "schedule";
type Action = CampaignPayload["action"];
type Errors = Record<string, string>;

const AUDIENCE_HELP: Record<Audience, string> = {
  all_subscribers: "Everyone who is subscribed",
  active_customers: "Paying customers, including VIPs",
  trial_users: "Contacts currently on a trial",
  vip_customers: "Your highest-value accounts",
};

interface FormState {
  name: string;
  subject: string;
  body: string;
  audience: Audience;
  mode: Mode;
  scheduledLocal: string;
}

const EMPTY: FormState = { name: "", subject: "", body: "", audience: "all_subscribers", mode: "now", scheduledLocal: "" };

function validate(form: FormState, action: Action, eligible: number | undefined): Errors {
  const errors: Errors = {};
  if (!form.name.trim()) errors.name = "Campaign name is required.";
  if (action === "draft") return errors;
  if (!form.subject.trim()) errors.subject = "Email subject is required.";
  if (!form.body.trim()) errors.body = "Message body is required.";
  if (eligible === 0) errors.audience = "This audience has no subscribed contacts.";
  if (action === "schedule") {
    const iso = jakartaInputToIso(form.scheduledLocal);
    if (!iso) errors.scheduled_at = "Choose a date and time.";
    else if (new Date(iso).getTime() <= Date.now()) errors.scheduled_at = "Scheduled time must be in the future.";
  }
  return errors;
}

export default function CampaignFormPage() {
  const { id } = useParams();
  const campaignId = id ? Number(id) : null;
  const isEdit = campaignId !== null;
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [form, setForm] = useState<FormState>(EMPTY);
  const [loaded, setLoaded] = useState(!isEdit);
  const [errors, setErrors] = useState<Errors>({});
  const [confirmSend, setConfirmSend] = useState(false);

  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta, refetchInterval: 5000 });
  const existing = useQuery({ queryKey: ["campaign", campaignId], queryFn: () => api.campaign(campaignId!), enabled: isEdit });

  // Populate once; later background refetches must never overwrite what the user typed.
  useEffect(() => {
    if (!loaded && existing.data) {
      const c = existing.data;
      setForm({
        name: c.name,
        subject: c.subject,
        body: c.body,
        audience: c.audience,
        mode: c.scheduled_at ? "schedule" : "now",
        scheduledLocal: c.scheduled_at ? toJakartaInput(new Date(c.scheduled_at)) : "",
      });
      setLoaded(true);
    }
  }, [existing.data, loaded]);

  const eligible = meta.data?.audiences.find((a) => a.value === form.audience)?.eligible;
  const audienceLabel = meta.data?.audiences.find((a) => a.value === form.audience)?.label;
  const minLocal = useMemo(() => toJakartaInput(new Date(Date.now() + 60_000)), [form.mode]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => {
      const fieldKey = key === "scheduledLocal" ? "scheduled_at" : key;
      if (!e[fieldKey]) return e;
      const next = { ...e };
      delete next[fieldKey];
      return next;
    });
  };

  const save = useMutation({
    mutationFn: (action: Action) => {
      const payload: CampaignPayload = {
        name: form.name,
        subject: form.subject,
        body: form.body,
        audience: form.audience,
        action,
        scheduled_at: action === "schedule" ? jakartaInputToIso(form.scheduledLocal) : null,
      };
      return isEdit ? api.updateCampaign(campaignId!, payload) : api.createCampaign(payload);
    },
    onSuccess: (campaign, action) => {
      queryClient.invalidateQueries();
      if (action === "draft") toast.success("Draft saved", { description: `“${campaign.name}” is saved as a draft.` });
      if (action === "schedule")
        toast.success("Campaign scheduled", { description: `“${campaign.name}” will be sent at ${formatDateTime(campaign.scheduled_at)}.` });
      if (action === "send") {
        if (campaign.status === "completed")
          toast.warning("Nothing to send", { description: campaign.status_note ?? "No eligible recipients." });
        else
          toast.success("Campaign is sending", {
            description:
              campaign.queue_published === false
                ? `${campaign.recipient_count} deliveries saved; they'll be queued automatically within a minute.`
                : `${campaign.recipient_count} deliveries queued.`,
          });
      }
      navigate(`/campaigns/${campaign.id}`);
    },
    onError: (error: Error) => {
      if (error instanceof ApiError && Object.keys(error.errors).length) setErrors(error.errors);
      toast.error("Couldn't save campaign", { description: error.message });
    },
  });

  const submit = (action: Action) => {
    const found = validate(form, action, eligible);
    setErrors(found);
    if (Object.keys(found).length) {
      toast.error("Please fix the highlighted fields.");
      return;
    }
    if (action === "send") setConfirmSend(true);
    else save.mutate(action);
  };

  if (isEdit && existing.error) return <ErrorState message={(existing.error as Error).message} onRetry={() => existing.refetch()} />;
  if (isEdit && !loaded) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-[480px] rounded-lg" />
      </div>
    );
  }
  if (isEdit && existing.data && !existing.data.can_edit) {
    return (
      <>
        <PageHeader title="This campaign can't be edited" description="Only drafts can be edited. Duplicate it to make changes to a copy." />
        <Button asChild variant="outline">
          <Link to={`/campaigns/${campaignId}`}>
            <ArrowLeft /> Back to campaign
          </Link>
        </Button>
      </>
    );
  }

  const primaryAction: Action = form.mode === "schedule" ? "schedule" : "send";
  const busy = save.isPending;

  return (
    <>
      <PageHeader
        eyebrow={
          <Link to={isEdit ? `/campaigns/${campaignId}` : "/campaigns"} className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" /> {isEdit ? "Back to campaign" : "Campaigns"}
          </Link>
        }
        title={isEdit ? "Edit draft" : "Create campaign"}
        description="Compose a plain-text email, choose who receives it, then send now or schedule it."
      />

      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          submit(primaryAction);
        }}
        className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]"
      >
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mail className="h-4 w-4 text-primary-strong" aria-hidden /> Message
              </CardTitle>
              <CardDescription>Email is the only channel in this demo. Messages are sent as plain text.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div>
                <Label htmlFor="name">Campaign name</Label>
                <p className="mb-1.5 mt-1 text-xs text-muted-foreground">Only visible to your team.</p>
                <Input id="name" value={form.name} maxLength={160} onChange={(e) => set("name", e.target.value)} aria-invalid={!!errors.name} aria-describedby="name-error" placeholder="e.g. November product update" />
                <FieldError id="name-error" message={errors.name} />
              </div>
              <div>
                <Label htmlFor="subject">Email subject</Label>
                <Input id="subject" className="mt-1.5" value={form.subject} maxLength={200} onChange={(e) => set("subject", e.target.value)} aria-invalid={!!errors.subject} aria-describedby="subject-error" placeholder="What recipients see in their inbox" />
                <FieldError id="subject-error" message={errors.subject} />
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="body">Message</Label>
                  <span className="text-xs tabular text-muted-foreground">{form.body.length.toLocaleString()} / 20,000</span>
                </div>
                <Textarea id="body" className="mt-1.5 min-h-[220px] leading-relaxed" value={form.body} maxLength={20000} onChange={(e) => set("body", e.target.value)} aria-invalid={!!errors.body} aria-describedby="body-error" placeholder="Write your message in plain text…" />
                <FieldError id="body-error" message={errors.body} />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-4 w-4 text-primary-strong" aria-hidden /> Audience
              </CardTitle>
              <CardDescription>Only subscribed contacts receive campaigns.</CardDescription>
            </CardHeader>
            <CardContent>
              <div role="radiogroup" aria-label="Audience" aria-describedby="audience-error" className="grid gap-3 sm:grid-cols-2">
                {(meta.data?.audiences ?? []).map((a) => {
                  const selected = form.audience === a.value;
                  return (
                    <button
                      key={a.value}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => set("audience", a.value)}
                      className={cn(
                        "flex items-start justify-between gap-3 rounded-lg border p-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        selected ? "border-primary bg-primary-soft ring-1 ring-primary" : "hover:bg-muted/50",
                      )}
                    >
                      <span>
                        <span className="block text-sm font-semibold">{a.label}</span>
                        <span className="block text-xs text-muted-foreground">{AUDIENCE_HELP[a.value]}</span>
                      </span>
                      <span className={cn("rounded-full px-2 py-0.5 text-xs font-semibold tabular", selected ? "bg-white text-primary-strong" : "bg-muted text-slate-600")}>
                        {a.eligible}
                      </span>
                    </button>
                  );
                })}
                {!meta.data && Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[66px] rounded-lg" />)}
              </div>
              <FieldError id="audience-error" message={errors.audience} />
              <p className="mt-3 flex items-start gap-2 rounded-md bg-muted/60 px-3 py-2 text-xs text-slate-600">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                <span>
                  <strong className="font-semibold">{eligible ?? "…"} eligible recipients right now.</strong> This count is a preview —
                  scheduled campaigns resolve their actual recipients at the moment they're sent.
                </span>
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarClock className="h-4 w-4 text-primary-strong" aria-hidden /> Delivery
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div role="radiogroup" aria-label="When to send" className="grid gap-3 sm:grid-cols-2">
                {(
                  [
                    { value: "now", title: "Send now", desc: "Start delivering immediately." },
                    { value: "schedule", title: "Schedule for later", desc: "Pick a date and time (WIB)." },
                  ] as const
                ).map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    role="radio"
                    aria-checked={form.mode === o.value}
                    onClick={() => set("mode", o.value)}
                    className={cn(
                      "rounded-lg border p-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      form.mode === o.value ? "border-primary bg-primary-soft ring-1 ring-primary" : "hover:bg-muted/50",
                    )}
                  >
                    <span className="block text-sm font-semibold">{o.title}</span>
                    <span className="block text-xs text-muted-foreground">{o.desc}</span>
                  </button>
                ))}
              </div>
              {form.mode === "schedule" && (
                <div>
                  <Label htmlFor="scheduled">Send time · {TZ_LABEL}</Label>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <Input
                      id="scheduled"
                      type="datetime-local"
                      step={60}
                      min={minLocal}
                      value={form.scheduledLocal}
                      onChange={(e) => set("scheduledLocal", e.target.value)}
                      aria-invalid={!!errors.scheduled_at}
                      aria-describedby="scheduled-error scheduled-help"
                      className="w-auto"
                    />
                    <Button type="button" variant="outline" size="sm" onClick={() => set("scheduledLocal", toJakartaInput(new Date(Date.now() + 120_000)))}>
                      In 2 minutes
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        const t = new Date(Date.now() + 86_400_000);
                        set("scheduledLocal", `${toJakartaInput(t).slice(0, 10)}T09:00`);
                      }}
                    >
                      Tomorrow 09:00
                    </Button>
                  </div>
                  <FieldError id="scheduled-error" message={errors.scheduled_at} />
                  <p id="scheduled-help" className="mt-2 text-xs text-muted-foreground">
                    Scheduling works to the minute. The scheduler checks for due campaigns once a minute, so sending starts shortly after the chosen time.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex flex-col-reverse gap-2 border-t pt-5 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" disabled={busy} onClick={() => submit("draft")}>
              <Save /> Save draft
            </Button>
            <Button type="submit" disabled={busy}>
              {form.mode === "schedule" ? <CalendarClock /> : <Send />}
              {busy ? "Saving…" : form.mode === "schedule" ? "Schedule campaign" : "Send now"}
            </Button>
          </div>
        </div>

        <aside className="xl:sticky xl:top-20 xl:self-start">
          <EmailPreview subject={form.subject} body={form.body} audience={audienceLabel ? `${audienceLabel} (${eligible ?? 0} contacts)` : undefined} />
        </aside>
      </form>

      <Dialog open={confirmSend} onOpenChange={setConfirmSend}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send “{form.name || "this campaign"}” now?</DialogTitle>
            <DialogDescription>
              It will be delivered to the {eligible ?? 0} subscribed contacts in {audienceLabel}. Delivery is simulated in this demo.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmSend(false)}>
              Not yet
            </Button>
            <Button
              disabled={busy}
              onClick={() => {
                setConfirmSend(false);
                save.mutate("send");
              }}
            >
              <Send /> Send now
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
