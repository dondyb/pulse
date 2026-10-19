import { AlertCircle, ChevronLeft, ChevronRight, type LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { Counts } from "@/lib/types";

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  eyebrow?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-2">{eyebrow}</div>}
        <h1 className="text-2xl font-bold text-foreground">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Pagination({
  page,
  pages,
  total,
  pageSize,
  onPage,
  noun = "results",
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
  noun?: string;
}) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return (
    <div className="flex items-center justify-between gap-3 border-t px-4 py-3 text-sm text-muted-foreground">
      <span className="tabular">
        {total === 0 ? `No ${noun}` : `Showing ${start}–${end} of ${total.toLocaleString()} ${noun}`}
      </span>
      <div className="flex items-center gap-2">
        <span className="hidden tabular sm:inline">
          Page {page} of {pages}
        </span>
        <Button variant="outline" size="icon" className="h-8 w-8" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeft />
        </Button>
        <Button variant="outline" size="icon" className="h-8 w-8" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-muted">
        <Icon className="h-5 w-5 text-muted-foreground" aria-hidden />
      </div>
      <p className="text-sm font-semibold">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      <span className="flex items-center gap-2">
        <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />
        {message}
      </span>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function TableSkeleton({ rows = 6, cols }: { rows?: number; cols: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <TableRow key={r} className="hover:bg-transparent">
          {Array.from({ length: cols }).map((__, c) => (
            <TableCell key={c}>
              <Skeleton className={cn("h-4", c === 0 ? "w-40" : "w-20")} />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

/** Segmented progress: delivered, failed and skipped are all terminal outcomes. */
export function DeliveryProgress({ counts, className, showLabel = true }: { counts: Counts; className?: string; showLabel?: boolean }) {
  const total = counts.total || 0;
  const pct = (n: number) => (total ? (n / total) * 100 : 0);
  const done = counts.delivered + counts.failed + counts.skipped;
  return (
    <div className={cn("min-w-[96px]", className)}>
      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-slate-100"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-label={`${done} of ${total} recipients processed`}
      >
        <div className="bg-primary transition-all duration-700" style={{ width: `${pct(counts.delivered)}%` }} />
        <div className="bg-red-500 transition-all duration-700" style={{ width: `${pct(counts.failed)}%` }} />
        <div className="bg-slate-400 transition-all duration-700" style={{ width: `${pct(counts.skipped)}%` }} />
      </div>
      {showLabel && (
        <p className="mt-1 text-xs tabular text-muted-foreground">
          {total ? `${done.toLocaleString()} / ${total.toLocaleString()}` : "—"}
        </p>
      )}
    </div>
  );
}

export function FieldError({ message, id }: { message?: string; id?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="mt-1.5 flex items-center gap-1 text-xs font-medium text-destructive">
      <AlertCircle className="h-3.5 w-3.5" aria-hidden />
      {message}
    </p>
  );
}
