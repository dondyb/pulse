import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleDashed,
  Clock,
  FileText,
  Hourglass,
  Loader2,
  MinusCircle,
  RotateCw,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { Campaign, JobStatus, RecipientStatus } from "@/lib/types";

type Tone = "neutral" | "info" | "progress" | "success" | "warning" | "danger" | "muted";

const TONES: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-700 ring-slate-200",
  info: "bg-sky-50 text-sky-800 ring-sky-200",
  progress: "bg-primary-soft text-primary-strong ring-emerald-200",
  success: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  warning: "bg-amber-50 text-amber-800 ring-amber-200",
  danger: "bg-red-50 text-red-700 ring-red-200",
  muted: "bg-slate-50 text-slate-500 ring-slate-200",
};

export function Badge({
  tone,
  icon: Icon,
  spin,
  children,
  className,
}: {
  tone: Tone;
  icon?: LucideIcon;
  spin?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset",
        TONES[tone],
        className,
      )}
    >
      {Icon && <Icon aria-hidden className={cn("h-3.5 w-3.5", spin && "animate-spin")} />}
      {children}
    </span>
  );
}

export function CampaignStatusBadge({ campaign }: { campaign: Pick<Campaign, "status" | "has_failures" | "awaiting_dispatch"> }) {
  switch (campaign.status) {
    case "draft":
      return <Badge tone="neutral" icon={FileText}>Draft</Badge>;
    case "scheduled":
      return campaign.awaiting_dispatch ? (
        <Badge tone="warning" icon={Hourglass}>Awaiting dispatch</Badge>
      ) : (
        <Badge tone="info" icon={Clock}>Scheduled</Badge>
      );
    case "processing":
      return <Badge tone="progress" icon={Loader2} spin>Sending</Badge>;
    case "completed":
      return campaign.has_failures ? (
        <Badge tone="warning" icon={AlertTriangle}>Completed with failures</Badge>
      ) : (
        <Badge tone="success" icon={CheckCircle2}>Completed</Badge>
      );
    case "cancelled":
      return <Badge tone="muted" icon={Ban}>Cancelled</Badge>;
  }
}

export function RecipientStatusBadge({ status }: { status: RecipientStatus }) {
  switch (status) {
    case "pending":
      return <Badge tone="neutral" icon={CircleDashed}>Pending</Badge>;
    case "delivered":
      return <Badge tone="success" icon={CheckCircle2}>Delivered</Badge>;
    case "failed":
      return <Badge tone="danger" icon={XCircle}>Failed</Badge>;
    case "skipped":
      return <Badge tone="muted" icon={MinusCircle}>Skipped</Badge>;
  }
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  switch (status) {
    case "queued":
      return <Badge tone="neutral" icon={CircleDashed}>Queued</Badge>;
    case "processing":
      return <Badge tone="progress" icon={Loader2} spin>Processing</Badge>;
    case "retrying":
      return <Badge tone="warning" icon={RotateCw}>Retrying</Badge>;
    case "delivered":
      return <Badge tone="success" icon={CheckCircle2}>Delivered</Badge>;
    case "failed":
      return <Badge tone="danger" icon={XCircle}>Failed</Badge>;
    case "skipped":
      return <Badge tone="muted" icon={MinusCircle}>Skipped</Badge>;
  }
}
