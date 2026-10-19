import { useQuery } from "@tanstack/react-query";
import { CalendarClock, CheckCircle2, Clock, Hourglass, Info, Megaphone, Plus, Send, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip as ChartTooltip, XAxis, YAxis } from "recharts";

import { ActivityFeed } from "@/components/ActivityFeed";
import { DeliveryProgress, EmptyState, ErrorState, PageHeader } from "@/components/common";
import { CampaignStatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { formatDateTime, formatNumber, formatPercent, formatRelative, shortDay } from "@/lib/format";
import type { Dashboard, Metric } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  draft: "#94a3b8",
  scheduled: "#38bdf8",
  processing: "#25CC9C",
  completed: "#0f8a66",
  completed_with_failures: "#f59e0b",
  cancelled: "#cbd5e1",
};

function MetricCard({
  label,
  metric,
  value,
  icon: Icon,
  sub,
}: {
  label: string;
  metric: Metric;
  value: string;
  icon: typeof Send;
  sub?: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <p className="flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground">
            {label}
            <Tooltip>
              <TooltipTrigger aria-label={`How ${label} is calculated`}>
                <Info className="h-3.5 w-3.5 text-slate-400" />
              </TooltipTrigger>
              <TooltipContent>{metric.definition}</TooltipContent>
            </Tooltip>
          </p>
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary-soft text-primary-strong">
            <Icon className="h-4 w-4" aria-hidden />
          </span>
        </div>
        <p className="mt-3 text-[28px] font-bold leading-none tabular">{value}</p>
        {sub && <p className="mt-2 text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function VolumeChart({ data }: { data: Dashboard["volume"] }) {
  const total = data.reduce((sum, d) => sum + d.delivered + d.failed, 0);
  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle>Delivery volume</CardTitle>
        <CardDescription>Final recipient outcomes per day, last 7 days (WIB)</CardDescription>
      </CardHeader>
      <CardContent className="h-[260px] pl-1">
        {total === 0 ? (
          <EmptyState icon={TrendingUp} title="No deliveries in the last 7 days" description="Send a campaign to see daily volume here." />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }} barCategoryGap="28%">
              <CartesianGrid vertical={false} stroke="#eef0f3" />
              <XAxis dataKey="date" tickFormatter={shortDay} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#64748b" }} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={36} tick={{ fontSize: 12, fill: "#64748b" }} />
              <ChartTooltip
                cursor={{ fill: "#f1f5f9" }}
                labelFormatter={(d: string) => shortDay(d)}
                contentStyle={{ borderRadius: 8, border: "1px solid #e4e7ec", fontSize: 12 }}
              />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="delivered" name="Delivered" stackId="a" fill="#25CC9C" isAnimationActive={false} />
              <Bar dataKey="failed" name="Failed" stackId="a" fill="#ef4444" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

function StatusBreakdown({ data }: { data: Dashboard["status_breakdown"] }) {
  const total = data.reduce((s, d) => s + d.count, 0);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Campaign status</CardTitle>
        <CardDescription>All {total} campaigns</CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-4">
        <div className="h-[140px] w-[140px] shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data.filter((d) => d.count > 0)} dataKey="count" nameKey="label" innerRadius={44} outerRadius={66} paddingAngle={2} stroke="none" isAnimationActive={false}>
                {data
                  .filter((d) => d.count > 0)
                  .map((d) => (
                    <Cell key={d.status} fill={STATUS_COLORS[d.status]} />
                  ))}
              </Pie>
              <ChartTooltip contentStyle={{ borderRadius: 8, border: "1px solid #e4e7ec", fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="flex-1 space-y-1.5 text-[13px]">
          {data.map((d) => (
            <li key={d.status} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-slate-600">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: STATUS_COLORS[d.status] }} aria-hidden />
                {d.label}
              </span>
              <span className="font-semibold tabular">{d.count}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function NextScheduled({ campaign }: { campaign: Dashboard["next_scheduled"] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-primary-strong" aria-hidden /> Next scheduled campaign
        </CardTitle>
      </CardHeader>
      <CardContent>
        {campaign ? (
          <Link to={`/campaigns/${campaign.id}`} className="block rounded-md border p-3 transition-colors hover:bg-muted/50">
            <div className="flex items-start justify-between gap-2">
              <p className="font-semibold leading-snug">{campaign.name}</p>
              <CampaignStatusBadge campaign={campaign} />
            </div>
            <p className="mt-2 text-sm text-slate-700">{formatDateTime(campaign.scheduled_at)}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {campaign.awaiting_dispatch ? "Awaiting scheduled dispatch" : formatRelative(campaign.scheduled_at)} ·{" "}
              {campaign.audience_label} · ~{campaign.recipient_count} recipients
            </p>
          </Link>
        ) : (
          <EmptyState icon={Clock} title="Nothing scheduled" description="Schedule a campaign to send it later." className="py-6" />
        )}
      </CardContent>
    </Card>
  );
}

function RecentCampaigns({ campaigns }: { campaigns: Dashboard["recent_campaigns"] }) {
  return (
    <Card className="lg:col-span-2">
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>Recent campaigns</CardTitle>
        </div>
        <Button asChild variant="link" size="sm" className="h-auto p-0">
          <Link to="/campaigns">View all</Link>
        </Button>
      </CardHeader>
      <CardContent className="px-0 pb-1">
        {campaigns.length === 0 ? (
          <EmptyState icon={Megaphone} title="No campaigns yet" />
        ) : (
          <ul className="divide-y">
            {campaigns.map((c) => (
              <li key={c.id}>
                <Link to={`/campaigns/${c.id}`} className="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-5 py-3 hover:bg-muted/40 sm:grid-cols-[1fr_150px_190px]">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">{c.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {c.audience_label} · {c.recipient_count_is_estimate ? "~" : ""}
                      {c.recipient_count} recipients
                    </p>
                  </div>
                  {c.counts.total > 0 ? (
                    <DeliveryProgress counts={c.counts} className="hidden sm:block" />
                  ) : (
                    <span className="hidden text-xs text-muted-foreground sm:block">
                      {c.status === "scheduled" ? formatRelative(c.scheduled_at) : "Not sent"}
                    </span>
                  )}
                  <span className="flex justify-end">
                    <CampaignStatusBadge campaign={c} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[124px] rounded-lg" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-[340px] rounded-lg lg:col-span-2" />
        <Skeleton className="h-[340px] rounded-lg" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 2000 });
  const m = data?.metrics;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="How your campaigns are performing right now."
        actions={
          <Button asChild size="lg">
            <Link to="/campaigns/new">
              <Plus /> Create campaign
            </Link>
          </Button>
        }
      />
      {error && !data && <ErrorState message={(error as Error).message} onRetry={() => refetch()} />}
      {isLoading && <DashboardSkeleton />}
      {data && m && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Delivered today" metric={m.delivered_today} value={formatNumber(m.delivered_today.value)} icon={Send} sub="Since midnight WIB" />
            <MetricCard
              label="Delivery success rate"
              metric={m.success_rate}
              value={formatPercent(m.success_rate.value)}
              icon={CheckCircle2}
              sub={`${formatNumber(m.success_rate.delivered)} of ${formatNumber((m.success_rate.delivered ?? 0) + (m.success_rate.failed ?? 0))} recipients · last 7 days`}
            />
            <MetricCard label="Pending deliveries" metric={m.pending_deliveries} value={formatNumber(m.pending_deliveries.value)} icon={Hourglass} sub="In campaigns currently sending" />
            <MetricCard label="Scheduled campaigns" metric={m.scheduled_campaigns} value={formatNumber(m.scheduled_campaigns.value)} icon={CalendarClock} sub="Waiting for their send time" />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <VolumeChart data={data.volume} />
            <div className="grid content-start gap-4 md:grid-cols-2 lg:grid-cols-1">
              <NextScheduled campaign={data.next_scheduled} />
              <StatusBreakdown data={data.status_breakdown} />
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <RecentCampaigns campaigns={data.recent_campaigns} />
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2" aria-hidden>
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
                  </span>
                  Live activity
                </CardTitle>
              </CardHeader>
              <CardContent className="max-h-[420px] overflow-y-auto">
                {data.activity.length ? <ActivityFeed events={data.activity} /> : <EmptyState icon={Info} title="No activity yet" />}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
