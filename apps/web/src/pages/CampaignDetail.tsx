import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Ban, Copy, Hourglass, Inbox, ListChecks, Pencil, RotateCcw, Search } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ActivityFeed } from "@/components/ActivityFeed";
import { DeliveryProgress, EmptyState, ErrorState, PageHeader, Pagination, TableSkeleton } from "@/components/common";
import { EmailPreview } from "@/components/EmailPreview";
import { Badge, CampaignStatusBadge, RecipientStatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCampaignActions } from "@/hooks/useCampaignActions";
import { useDebounced } from "@/hooks/useDebounced";
import { api } from "@/lib/api";
import { formatDateTime, formatPercent, formatRelative, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CampaignDetail, Recipient } from "@/lib/types";

const FILTERS = [
  { value: "", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "delivered", label: "Delivered" },
  { value: "failed", label: "Failed" },
  { value: "skipped", label: "Skipped" },
] as const;

function Stat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-lg border bg-card px-4 py-3 shadow-card">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-2xl font-bold tabular", tone)}>{value.toLocaleString()}</p>
    </div>
  );
}

function ProgressCard({ campaign }: { campaign: CampaignDetail }) {
  const { counts } = campaign;
  const done = counts.delivered + counts.failed + counts.skipped;
  const live = campaign.status === "processing";
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>Delivery progress</CardTitle>
          <CardDescription>
            {campaign.status === "draft" && "Not sent yet."}
            {campaign.status === "scheduled" &&
              (campaign.awaiting_dispatch ? "The send time has passed; the scheduler will start this campaign shortly." : `Starts sending ${formatRelative(campaign.scheduled_at)}.`)}
            {campaign.status === "cancelled" && "This campaign was cancelled before sending."}
            {(live || campaign.status === "completed") &&
              `${done.toLocaleString()} of ${counts.total.toLocaleString()} recipients reached a final outcome.`}
          </CardDescription>
        </div>
        {live && <Badge tone="progress">Live</Badge>}
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="mb-1.5 flex items-baseline justify-between text-sm">
            <span className="font-semibold tabular">{formatPercent(campaign.progress, 0)}</span>
            {campaign.status_note && <span className="text-xs text-muted-foreground">{campaign.status_note}</span>}
          </div>
          <DeliveryProgress counts={counts} showLabel={false} className="[&>div]:h-3" />
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-primary" aria-hidden />Delivered</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-red-500" aria-hidden />Failed</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-slate-400" aria-hidden />Skipped</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-slate-100 ring-1 ring-slate-300" aria-hidden />Pending</span>
          </div>
        </div>
        {campaign.runs.length > 0 && (
          <ul className="divide-y rounded-md border text-sm">
            {campaign.runs.map((run) => (
              <li key={run.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <span>
                  <span className="font-medium">{run.kind === "initial" ? "Initial send" : `Retry of failed deliveries`}</span>
                  <span className="text-muted-foreground"> · {run.job_count} recipients · {formatDateTime(run.created_at)}</span>
                </span>
                {run.status === "active" ? <Badge tone="progress">In progress</Badge> : <Badge tone="neutral">Finished</Badge>}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function AttemptsDialog({ campaignId, recipient, onClose }: { campaignId: number; recipient: Recipient | null; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["attempts", campaignId, recipient?.id],
    queryFn: () => api.recipientAttempts(campaignId, recipient!.id),
    enabled: !!recipient,
    refetchInterval: 2000,
  });
  return (
    <Dialog open={!!recipient} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Delivery history</DialogTitle>
          <DialogDescription>
            {recipient?.name} · {recipient?.email}
          </DialogDescription>
        </DialogHeader>
        {isLoading && <Skeleton className="h-24" />}
        {data && data.items.length === 0 && <p className="text-sm text-muted-foreground">No delivery attempts were made for this recipient.</p>}
        {data && data.items.length > 0 && (
          <ol className="space-y-2">
            {data.items.map((a) => (
              <li key={a.id} className="rounded-md border px-3 py-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">
                    {a.run_number > 1 ? `Retry run ${a.run_number - 1} · ` : ""}Attempt {a.attempt_number}
                  </span>
                  {a.outcome === "success" && <Badge tone="success">Delivered</Badge>}
                  {a.outcome === "failure" && <Badge tone="danger">Failed</Badge>}
                  {a.outcome === "in_progress" && <Badge tone="progress">In progress</Badge>}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(a.started_at)} · {formatTime(a.started_at)}</p>
                {a.error && <p className="mt-1 text-xs text-red-700">{a.error}</p>}
              </li>
            ))}
          </ol>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Recipients({ campaign }: { campaign: CampaignDetail }) {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Recipient | null>(null);
  const q = useDebounced(search);
  const live = campaign.status === "processing";
  const { data, isLoading } = useQuery({
    queryKey: ["recipients", campaign.id, status, q, page],
    queryFn: () => api.recipients(campaign.id, { status, search: q, page, page_size: 10 }),
    placeholderData: keepPreviousData,
    refetchInterval: live ? 2000 : false,
  });

  if (campaign.counts.total === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Recipients</CardTitle>
        </CardHeader>
        <EmptyState
          icon={Inbox}
          title={campaign.status === "completed" ? "No eligible recipients" : "Recipients are chosen when the campaign is sent"}
          description={
            campaign.status === "completed"
              ? "No subscribed contacts matched this audience when the campaign was sent."
              : `Right now about ${campaign.recipient_count} subscribed contacts match ${campaign.audience_label}.`
          }
        />
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-center sm:justify-between sm:space-y-0">
        <CardTitle>Recipients</CardTitle>
        <div className="relative sm:w-64">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} placeholder="Search name or email" className="h-8 pl-9" aria-label="Search recipients" />
        </div>
      </CardHeader>
      <div className="flex gap-1 overflow-x-auto px-5 pb-3" role="tablist" aria-label="Filter recipients">
        {FILTERS.map((f) => {
          const n = f.value ? campaign.counts[f.value] : campaign.counts.total;
          return (
            <button
              key={f.value}
              role="tab"
              aria-selected={status === f.value}
              onClick={() => { setStatus(f.value); setPage(1); }}
              className={cn(
                "whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-semibold transition-colors",
                status === f.value ? "bg-foreground text-white" : "text-slate-600 hover:bg-muted",
              )}
            >
              {f.label} <span className="tabular opacity-70">{n}</span>
            </button>
          );
        })}
      </div>
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Recipient</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Attempts</TableHead>
            <TableHead>Last update</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading && <TableSkeleton cols={4} rows={5} />}
          {data?.items.map((r) => (
            <TableRow key={r.id} className="cursor-pointer" onClick={() => setSelected(r)} title="View delivery history">
              <TableCell className="max-w-[260px]">
                <p className="truncate font-medium">{r.name}</p>
                <p className="truncate text-xs text-muted-foreground">{r.email}</p>
                {r.last_error && r.status !== "delivered" && <p className="mt-0.5 truncate text-xs text-red-700">{r.last_error}</p>}
              </TableCell>
              <TableCell>
                <RecipientStatusBadge status={r.status} />
              </TableCell>
              <TableCell className="text-right tabular">{r.attempt_count}</TableCell>
              <TableCell className="whitespace-nowrap text-xs text-muted-foreground" title={formatDateTime(r.updated_at)}>
                {formatRelative(r.updated_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {data && data.items.length === 0 && <EmptyState icon={Inbox} title="No recipients match" className="py-8" />}
      {data && data.total > 0 && <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={10} onPage={setPage} noun="recipients" />}
      <AttemptsDialog campaignId={campaign.id} recipient={selected} onClose={() => setSelected(null)} />
    </Card>
  );
}

function Timeline({ campaignId, live }: { campaignId: number; live: boolean }) {
  const [milestones, setMilestones] = useState(true);
  const { data } = useQuery({
    queryKey: ["campaignActivity", campaignId, milestones],
    queryFn: () => api.campaignActivity(campaignId, milestones),
    refetchInterval: live ? 2000 : 10000,
  });
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Delivery activity</CardTitle>
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setMilestones((m) => !m)} aria-pressed={!milestones}>
          {milestones ? "Show every delivery" : "Key events only"}
        </Button>
      </CardHeader>
      <CardContent className="max-h-[440px] overflow-y-auto">
        {!data && <Skeleton className="h-32" />}
        {data && (data.items.length ? <ActivityFeed events={data.items} showCampaign={false} /> : <EmptyState icon={ListChecks} title="No activity yet" className="py-6" />)}
      </CardContent>
    </Card>
  );
}

export default function CampaignDetailPage() {
  const campaignId = Number(useParams().id);
  const actions = useCampaignActions();
  const { data: c, isLoading, error, refetch } = useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => api.campaign(campaignId),
    refetchInterval: (q) => (q.state.data && ["processing", "scheduled"].includes(q.state.data.status) ? 2000 : 8000),
  });

  if (error && !c) return <ErrorState message={(error as Error).message} onRetry={() => refetch()} />;
  if (isLoading || !c) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-12 w-96" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[74px]" />)}</div>
        <Skeleton className="h-[200px]" />
      </div>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <Link to="/campaigns" className="inline-flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" /> Campaigns
          </Link>
        }
        title={
          <span className="flex flex-wrap items-center gap-3">
            {c.name} <CampaignStatusBadge campaign={c} />
          </span>
        }
        description={`${c.audience_label} · Email · Created ${formatDateTime(c.created_at)}`}
        actions={
          <>
            {c.can_edit && (
              <Button asChild variant="outline">
                <Link to={`/campaigns/${c.id}/edit`}>
                  <Pencil /> Edit draft
                </Link>
              </Button>
            )}
            <Button variant="outline" onClick={() => actions.duplicate.mutate(c)} disabled={actions.duplicate.isPending}>
              <Copy /> Duplicate
            </Button>
            {c.can_cancel && (
              <Button variant="outline" className="text-destructive hover:text-destructive" onClick={() => actions.requestCancel(c)}>
                <Ban /> Cancel
              </Button>
            )}
            {c.can_retry && (
              <Button onClick={() => actions.retry.mutate(c)} disabled={actions.retry.isPending}>
                <RotateCcw /> {actions.retry.isPending ? "Starting…" : `Retry ${c.counts.failed} failed`}
              </Button>
            )}
          </>
        }
      />

      {c.awaiting_dispatch && (
        <div role="status" className="mb-6 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <Hourglass className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <div>
            <p className="font-semibold">Awaiting scheduled dispatch</p>
            <p className="text-amber-800">
              The send time ({formatDateTime(c.scheduled_at)}) has passed. The scheduler runs once a minute and will start this campaign on its next run.
            </p>
          </div>
        </div>
      )}

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Total recipients" value={c.counts.total} />
        <Stat label="Pending" value={c.counts.pending} />
        <Stat label="Delivered" value={c.counts.delivered} tone="text-emerald-700" />
        <Stat label="Failed" value={c.counts.failed} tone={c.counts.failed ? "text-red-700" : undefined} />
        <Stat label="Skipped" value={c.counts.skipped} tone="text-slate-500" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0 space-y-6">
          <ProgressCard campaign={c} />
          <Recipients campaign={c} />
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Schedule</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[110px_1fr] gap-y-2 text-sm">
                <dt className="text-muted-foreground">Scheduled for</dt>
                <dd>{c.scheduled_at ? formatDateTime(c.scheduled_at) : c.status === "draft" ? "Not scheduled" : "Sent immediately"}</dd>
                <dt className="text-muted-foreground">Started</dt>
                <dd>{formatDateTime(c.dispatched_at)}</dd>
                <dt className="text-muted-foreground">{c.status === "cancelled" ? "Cancelled" : "Finished"}</dt>
                <dd>{formatDateTime(c.status === "cancelled" ? c.cancelled_at : c.completed_at)}</dd>
              </dl>
            </CardContent>
          </Card>
          <EmailPreview subject={c.subject} body={c.body} audience={c.audience_label} />
          <Timeline campaignId={c.id} live={c.status === "processing"} />
        </div>
      </div>
      {actions.cancelDialog}
    </>
  );
}
