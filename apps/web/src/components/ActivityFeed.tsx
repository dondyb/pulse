import { AlertTriangle, CheckCircle2, Info, Send, XCircle } from "lucide-react";
import { Link } from "react-router-dom";

import { formatRelative, formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ActivityEvent } from "@/lib/types";

const LEVEL = {
  info: { icon: Info, cls: "bg-sky-50 text-sky-700" },
  success: { icon: CheckCircle2, cls: "bg-emerald-50 text-emerald-700" },
  warning: { icon: AlertTriangle, cls: "bg-amber-50 text-amber-700" },
  error: { icon: XCircle, cls: "bg-red-50 text-red-700" },
} as const;

export function ActivityFeed({ events, showCampaign = true }: { events: ActivityEvent[]; showCampaign?: boolean }) {
  return (
    <ol className="relative space-y-0">
      {events.map((event, i) => {
        const level = LEVEL[event.level] ?? LEVEL.info;
        const Icon = event.kind === "campaign.dispatched" ? Send : level.icon;
        return (
          <li key={event.id} className="relative flex gap-3 pb-4 last:pb-0">
            {i < events.length - 1 && <span aria-hidden className="absolute left-[13px] top-7 h-[calc(100%-1.5rem)] w-px bg-border" />}
            <span className={cn("z-10 mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full", level.cls)}>
              <Icon className="h-3.5 w-3.5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm leading-snug text-foreground [overflow-wrap:anywhere]">{event.message}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                <time dateTime={event.created_at} title={formatDateTime(event.created_at)}>
                  {formatRelative(event.created_at)}
                </time>
                {showCampaign && event.campaign_id && event.campaign_name && (
                  <>
                    {" · "}
                    <Link to={`/campaigns/${event.campaign_id}`} className="font-medium text-primary-strong hover:underline">
                      {event.campaign_name}
                    </Link>
                  </>
                )}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
