import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Ban, Copy, Eye, Megaphone, MoreHorizontal, Pencil, Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { DeliveryProgress, EmptyState, ErrorState, PageHeader, Pagination, TableSkeleton } from "@/components/common";
import { CampaignStatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCampaignActions } from "@/hooks/useCampaignActions";
import { useDebounced } from "@/hooks/useDebounced";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, formatShortDateTime } from "@/lib/format";

const PAGE_SIZE = 10;
const STATUSES = [
  { value: "all", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "scheduled", label: "Scheduled" },
  { value: "processing", label: "Sending" },
  { value: "completed", label: "Completed" },
  { value: "completed_with_failures", label: "Completed with failures" },
  { value: "cancelled", label: "Cancelled" },
];

export default function CampaignsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 1);
  const status = params.get("status") ?? "all";
  const [search, setSearch] = useState(params.get("q") ?? "");
  const debounced = useDebounced(search);
  const actions = useCampaignActions();

  useEffect(() => {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (debounced) next.set("q", debounced);
        else next.delete("q");
        if ((prev.get("q") ?? "") !== debounced) next.delete("page");
        return next;
      },
      { replace: true },
    );
  }, [debounced, setParams]);

  const update = (key: string, value: string | null) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value);
      else next.delete(key);
      if (key !== "page") next.delete("page");
      return next;
    });

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ["campaigns", { page, status, q: debounced }],
    queryFn: () => api.campaigns({ page, page_size: PAGE_SIZE, status: status === "all" ? undefined : status, search: debounced }),
    placeholderData: keepPreviousData,
    refetchInterval: 2000,
  });

  const filtered = !!debounced || status !== "all";

  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Create, schedule and track your email campaigns."
        actions={
          <Button asChild>
            <Link to="/campaigns/new">
              <Plus /> Create campaign
            </Link>
          </Button>
        }
      />
      <Card>
        <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center">
          <div className="relative flex-1 sm:max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search campaigns by name"
              className="pl-9"
              aria-label="Search campaigns"
            />
          </div>
          <Select value={status} onValueChange={(v) => update("status", v === "all" ? null : v)}>
            <SelectTrigger className="sm:w-56" aria-label="Filter by status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUSES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {isFetching && !isLoading && <span className="text-xs text-muted-foreground sm:ml-auto">Updating…</span>}
        </div>
        {error && !data && (
          <div className="p-4">
            <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
          </div>
        )}
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Campaign</TableHead>
              <TableHead>Audience</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Recipients</TableHead>
              <TableHead>Progress</TableHead>
              <TableHead>Scheduled</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="w-12">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <TableSkeleton cols={8} />}
            {data?.items.map((c) => (
              <TableRow key={c.id} className="cursor-pointer" onClick={() => navigate(`/campaigns/${c.id}`)}>
                <TableCell className="max-w-[240px]">
                  <Link to={`/campaigns/${c.id}`} className="block truncate font-semibold hover:underline" onClick={(e) => e.stopPropagation()}>
                    {c.name}
                  </Link>
                  <p className="truncate text-xs text-muted-foreground">{c.subject || "No subject"}</p>
                </TableCell>
                <TableCell className="whitespace-nowrap text-slate-600">{c.audience_label}</TableCell>
                <TableCell>
                  <CampaignStatusBadge campaign={c} />
                </TableCell>
                <TableCell className="text-right tabular">
                  {c.recipient_count_is_estimate ? (
                    <span title="Estimated: recipients are resolved when the campaign is sent">~{c.recipient_count}</span>
                  ) : (
                    c.recipient_count.toLocaleString()
                  )}
                </TableCell>
                <TableCell>
                  {c.status === "processing" || c.status === "completed" ? (
                    <DeliveryProgress counts={c.counts} />
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap text-slate-600" title={c.scheduled_at ? formatDateTime(c.scheduled_at) : undefined}>
                  {c.scheduled_at ? `${formatShortDateTime(c.scheduled_at)} WIB` : "—"}
                </TableCell>
                <TableCell className="whitespace-nowrap text-slate-600">{formatDate(c.created_at)}</TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={`Actions for ${c.name}`}>
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => navigate(`/campaigns/${c.id}`)}>
                        <Eye /> View details
                      </DropdownMenuItem>
                      {c.can_edit && (
                        <DropdownMenuItem onSelect={() => navigate(`/campaigns/${c.id}/edit`)}>
                          <Pencil /> Edit draft
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuItem onSelect={() => actions.duplicate.mutate(c)}>
                        <Copy /> Duplicate as draft
                      </DropdownMenuItem>
                      {c.can_cancel && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => actions.requestCancel(c)}>
                            <Ban className="!text-destructive" /> Cancel campaign
                          </DropdownMenuItem>
                        </>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {data && data.items.length === 0 && (
          <EmptyState
            icon={Megaphone}
            title={filtered ? "No campaigns match your filters" : "No campaigns yet"}
            description={filtered ? "Try a different search or status." : "Create your first campaign to reach your contacts."}
            action={
              filtered ? (
                <Button variant="outline" onClick={() => { setSearch(""); setParams({}); }}>
                  Clear filters
                </Button>
              ) : (
                <Button asChild>
                  <Link to="/campaigns/new">Create campaign</Link>
                </Button>
              )
            }
          />
        )}
        {data && data.total > 0 && (
          <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={PAGE_SIZE} onPage={(p) => update("page", String(p))} noun="campaigns" />
        )}
      </Card>
      {actions.cancelDialog}
    </>
  );
}
