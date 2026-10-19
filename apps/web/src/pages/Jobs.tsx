import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Clock, Cpu, Database, ListTodo, Search, Timer } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState, ErrorState, PageHeader, Pagination, TableSkeleton } from "@/components/common";
import { Badge, JobStatusBadge } from "@/components/StatusBadge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDebounced } from "@/hooks/useDebounced";
import { api } from "@/lib/api";
import { formatDateTime, formatRelative, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CronRun, JobStatus, JobSummary } from "@/lib/types";

const PAGE_SIZE = 20;
const STATUSES: { value: JobStatus; label: string; tone: string }[] = [
  { value: "queued", label: "Queued", tone: "text-slate-700" },
  { value: "processing", label: "Processing", tone: "text-primary-strong" },
  { value: "retrying", label: "Retrying", tone: "text-amber-700" },
  { value: "delivered", label: "Delivered", tone: "text-emerald-700" },
  { value: "failed", label: "Failed", tone: "text-red-700" },
  { value: "skipped", label: "Skipped", tone: "text-slate-500" },
];

function CronRunLine({ run, label }: { run: CronRun | null; label: string }) {
  return (
    <div>
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">
        {run ? (
          <>
            <span title={formatDateTime(run.started_at)}>{formatRelative(run.started_at)}</span>
            <span className="text-muted-foreground"> · {formatTime(run.started_at)} WIB</span>
          </>
        ) : (
          <span className="text-muted-foreground">Never</span>
        )}
      </dd>
    </div>
  );
}

function Services({ summary }: { summary: JobSummary }) {
  const { cron } = summary;
  const last = cron.last_run;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-primary-strong" aria-hidden /> Delivery worker
          </CardTitle>
          <CardDescription>
            Continuous process consuming the NATS JetStream consumer · concurrency {summary.settings.worker_concurrency} · up to{" "}
            {summary.settings.max_attempts} attempts, retry delays {summary.settings.retry_delays_seconds.join("s, ")}s
          </CardDescription>
        </CardHeader>
        <CardContent>
          {summary.workers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No worker heartbeat recorded in the last 24 hours.</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {summary.workers.map((w) => (
                <li key={w.worker_id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span className="font-mono text-xs">{w.worker_id}</span>
                  <span className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground" title={formatDateTime(w.last_seen_at)}>
                      Last seen {formatRelative(w.last_seen_at)} · {w.jobs_processed} attempts this session
                    </span>
                    {w.online ? (
                      <Badge tone="success">Online</Badge>
                    ) : w.status === "stopped" ? (
                      <Badge tone="muted">Stopped</Badge>
                    ) : (
                      <Badge tone="danger">Unresponsive</Badge>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Database className="h-3.5 w-3.5" aria-hidden />
            Outbox records waiting to be published: <strong className="tabular text-foreground">{summary.outbox_pending}</strong>
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Timer className="h-4 w-4 text-primary-strong" aria-hidden /> Scheduler (cron)
          </CardTitle>
          <CardDescription>
            One-shot <code className="rounded bg-muted px-1 text-[12px]">python -m app.tasks.dispatch_due</code> run by Supercronic {cron.schedule}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <CronRunLine run={last} label="Last run" />
            <CronRunLine run={cron.last_success} label="Last successful run" />
            <div>
              <dt className="text-xs font-medium text-muted-foreground">Last result</dt>
              <dd className="mt-1">
                {!last ? (
                  <span className="text-sm text-muted-foreground">—</span>
                ) : last.status === "success" ? (
                  <Badge tone="success">Succeeded</Badge>
                ) : last.status === "running" ? (
                  <Badge tone="progress">Running</Badge>
                ) : (
                  <Badge tone="danger">Failed</Badge>
                )}
              </dd>
            </div>
          </dl>
          {last?.error && <p className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-800">{last.error}</p>}
          <div className="overflow-hidden rounded-md border">
            <table className="w-full text-xs">
              <thead className="bg-muted/60 text-left text-muted-foreground">
                <tr>
                  <th className="px-3 py-1.5 font-semibold">Started</th>
                  <th className="px-3 py-1.5 font-semibold">Result</th>
                  <th className="px-3 py-1.5 text-right font-semibold">Dispatched</th>
                  <th className="px-3 py-1.5 text-right font-semibold">Published</th>
                  <th className="px-3 py-1.5 text-right font-semibold">Duration</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {cron.recent_runs.slice(0, 5).map((r) => (
                  <tr key={r.id}>
                    <td className="px-3 py-1.5 tabular">{formatTime(r.started_at)}</td>
                    <td className={cn("px-3 py-1.5 font-medium", r.status === "failed" ? "text-red-700" : r.status === "success" ? "text-emerald-700" : "")}>
                      {r.status === "success" ? "Succeeded" : r.status === "failed" ? "Failed" : "Running"}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular">{r.campaigns_dispatched}</td>
                    <td className="px-3 py-1.5 text-right tabular">{r.outbox_published}</td>
                    <td className="px-3 py-1.5 text-right tabular">{r.duration_ms !== null ? `${r.duration_ms} ms` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function JobsPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const campaignId = params.get("campaign_id") ?? "";
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebounced(search);
  useEffect(() => setPage(1), [q, status, campaignId]);

  const summary = useQuery({ queryKey: ["jobSummary"], queryFn: api.jobSummary, refetchInterval: 2000 });
  const jobs = useQuery({
    queryKey: ["jobs", { status, campaignId, q, page }],
    queryFn: () => api.jobs({ status, campaign_id: campaignId, search: q, page, page_size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
    refetchInterval: 2000,
  });

  const setStatus = (value: string) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value && value !== status) next.set("status", value);
      else next.delete("status");
      return next;
    });

  return (
    <>
      <PageHeader title="Job Activity" description="Technical view of the delivery queue, worker and scheduler. Updates every 2 seconds." />

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {STATUSES.map((s) => (
          <button
            key={s.value}
            onClick={() => setStatus(s.value)}
            aria-pressed={status === s.value}
            className={cn(
              "rounded-lg border bg-card px-4 py-3 text-left shadow-card transition-colors hover:border-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              status === s.value && "border-primary ring-1 ring-primary",
            )}
          >
            <p className="text-xs font-medium text-muted-foreground">{s.label}</p>
            {summary.data ? (
              <p className={cn("mt-1 text-2xl font-bold tabular", s.tone)}>{summary.data.counts[s.value].toLocaleString()}</p>
            ) : (
              <Skeleton className="mt-2 h-6 w-12" />
            )}
          </button>
        ))}
      </div>

      {summary.error && !summary.data && <ErrorState message={(summary.error as Error).message} onRetry={() => summary.refetch()} />}
      {summary.data ? <Services summary={summary.data} /> : <Skeleton className="h-[260px] rounded-lg" />}

      <Card className="mt-6">
        <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center">
          <div className="relative flex-1 sm:max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search recipient email" className="pl-9" aria-label="Search jobs by recipient email" />
          </div>
          <div className="flex flex-wrap items-center gap-1" role="tablist" aria-label="Filter jobs by status">
            {[{ value: "", label: "All" }, ...STATUSES].map((s) => (
              <button
                key={s.value}
                role="tab"
                aria-selected={status === s.value}
                onClick={() => setStatus(s.value)}
                className={cn(
                  "rounded-md px-2.5 py-1 text-xs font-semibold transition-colors",
                  status === s.value ? "bg-foreground text-white" : "text-slate-600 hover:bg-muted",
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
          {campaignId && (
            <button className="text-xs font-medium text-primary-strong hover:underline sm:ml-auto" onClick={() => setParams((p) => { const n = new URLSearchParams(p); n.delete("campaign_id"); return n; })}>
              Campaign #{campaignId} · clear
            </button>
          )}
        </div>
        {jobs.error && !jobs.data && (
          <div className="p-4">
            <ErrorState message={(jobs.error as Error).message} onRetry={() => jobs.refetch()} />
          </div>
        )}
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Job</TableHead>
              <TableHead>Campaign</TableHead>
              <TableHead>Recipient</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Attempts</TableHead>
              <TableHead>Last error</TableHead>
              <TableHead>Next retry</TableHead>
              <TableHead>Processing (WIB)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.isLoading && <TableSkeleton cols={8} rows={8} />}
            {jobs.data?.items.map((j) => (
              <TableRow key={j.id}>
                <TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">
                  #{j.id}
                  {j.run_kind === "manual_retry" && <span className="ml-1 rounded bg-sky-50 px-1 font-sans text-[10px] font-semibold text-sky-700">RETRY RUN</span>}
                </TableCell>
                <TableCell className="max-w-[180px]">
                  <Link to={`/campaigns/${j.campaign_id}`} className="block truncate font-medium hover:underline">
                    {j.campaign_name}
                  </Link>
                </TableCell>
                <TableCell className="max-w-[200px] truncate text-slate-600" title={j.recipient_email}>{j.recipient_email}</TableCell>
                <TableCell>
                  <JobStatusBadge status={j.status} />
                </TableCell>
                <TableCell className="text-right tabular">
                  {j.attempts}/{j.max_attempts}
                </TableCell>
                <TableCell className="max-w-[200px] truncate text-xs text-red-700" title={j.last_error ?? undefined}>
                  {j.last_error ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs">
                  {j.next_attempt_at ? (
                    <span className="inline-flex items-center gap-1 text-amber-800">
                      <Clock className="h-3 w-3" aria-hidden />
                      {formatRelative(j.next_attempt_at)}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs tabular text-slate-600">
                  <span title={`Started ${formatDateTime(j.first_started_at)}`}>{j.first_started_at ? formatTime(j.first_started_at) : "Not started"}</span>
                  {j.finished_at && <span className="block text-muted-foreground" title={`Finished ${formatDateTime(j.finished_at)}`}>→ {formatTime(j.finished_at)}</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {jobs.data && jobs.data.items.length === 0 && <EmptyState icon={ListTodo} title="No jobs match" description="Jobs appear here when a campaign starts sending." />}
        {jobs.data && jobs.data.total > 0 && (
          <Pagination page={jobs.data.page} pages={jobs.data.pages} total={jobs.data.total} pageSize={PAGE_SIZE} onPage={setPage} noun="jobs" />
        )}
      </Card>
    </>
  );
}
