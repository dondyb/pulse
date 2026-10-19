import { useQuery } from "@tanstack/react-query";
import { Activity, FlaskConical, LayoutDashboard, Megaphone, Plus, Users } from "lucide-react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/campaigns", label: "Campaigns", icon: Megaphone },
  { to: "/contacts", label: "Contacts", icon: Users },
  { to: "/jobs", label: "Job Activity", icon: Activity },
];

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2.5" aria-label="Pulse home">
      <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#25CC9C" />
        <path d="M6 17h5l2.5-6 4 11 3-8H26" fill="none" stroke="#06261c" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {!compact && <span className="text-[17px] font-bold tracking-tight">Pulse</span>}
    </Link>
  );
}

function WorkerStatus() {
  const { data } = useQuery({ queryKey: ["jobSummary"], queryFn: api.jobSummary, refetchInterval: 5000 });
  const online = data?.workers.some((w) => w.online);
  if (!data) return null;
  return (
    <Link
      to="/jobs"
      className="hidden items-center gap-1.5 rounded-full px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted md:inline-flex"
    >
      <span className={cn("h-2 w-2 rounded-full", online ? "bg-primary" : "bg-amber-500")} aria-hidden />
      {online ? "Delivery service running" : "Delivery service offline"}
    </Link>
  );
}

export function Layout() {
  return (
    <div className="min-h-screen">
      {/* Sidebar: full on desktop, icon rail on tablet */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-16 flex-col border-r bg-card md:flex lg:w-60">
        <div className="flex h-14 items-center border-b px-4">
          <div className="lg:hidden">
            <Logo compact />
          </div>
          <div className="hidden lg:block">
            <Logo />
          </div>
        </div>
        <nav className="flex-1 space-y-1 p-3" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <Tooltip key={to}>
              {/* Wrapper element: Slot would otherwise stringify NavLink's className function. */}
              <TooltipTrigger asChild>
                <div>
                <NavLink
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary-soft text-primary-strong"
                        : "text-slate-600 hover:bg-muted hover:text-foreground",
                    )
                  }
                >
                  <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
                  <span className="hidden lg:inline">{label}</span>
                </NavLink>
                </div>
              </TooltipTrigger>
              <TooltipContent side="right" className="lg:hidden">
                {label}
              </TooltipContent>
            </Tooltip>
          ))}
        </nav>
        <div className="hidden border-t p-4 text-xs text-muted-foreground lg:block">
          <p className="font-semibold text-foreground">Nusantara Demo Workspace</p>
          <p className="mt-0.5">Times shown in WIB (UTC+7)</p>
        </div>
      </aside>

      <div className="md:pl-16 lg:pl-60">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b bg-card/90 px-4 backdrop-blur sm:px-6">
          <div className="flex items-center gap-3 md:hidden">
            <Logo compact />
          </div>
          <div className="flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">
                  <FlaskConical className="h-3.5 w-3.5" aria-hidden />
                  Demo mode — deliveries are simulated
                </span>
              </TooltipTrigger>
              <TooltipContent>No real emails are sent. Delivery outcomes are simulated and repeatable.</TooltipContent>
            </Tooltip>
            <WorkerStatus />
          </div>
          <Button asChild size="sm">
            <Link to="/campaigns/new">
              <Plus /> Create campaign
            </Link>
          </Button>
        </header>

        {/* Mobile nav */}
        <nav className="flex gap-1 overflow-x-auto border-b bg-card px-3 py-2 md:hidden" aria-label="Main">
          {NAV.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn("whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium", isActive ? "bg-primary-soft text-primary-strong" : "text-slate-600")
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>

        <main className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
