import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellOff, BellRing, MoreHorizontal, Pencil, Search, UserPlus, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, FieldError, PageHeader, Pagination, TableSkeleton } from "@/components/common";
import { Badge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDebounced } from "@/hooks/useDebounced";
import { ApiError, api, type ContactPayload } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Contact, Segment } from "@/lib/types";

const PAGE_SIZE = 20;
const SEGMENTS: { value: Segment; label: string }[] = [
  { value: "active_customer", label: "Active customer" },
  { value: "trial_user", label: "Trial user" },
  { value: "vip_customer", label: "VIP customer" },
  { value: "prospect", label: "Prospect" },
];
const SEGMENT_LABEL = Object.fromEntries(SEGMENTS.map((s) => [s.value, s.label])) as Record<Segment, string>;
const SEGMENT_TONE: Record<Segment, "info" | "progress" | "warning" | "neutral"> = {
  active_customer: "progress",
  trial_user: "info",
  vip_customer: "warning",
  prospect: "neutral",
};

const EMPTY: ContactPayload = { name: "", email: "", company: "", segment: "active_customer", subscribed: true };

function ContactDialog({ open, contact, onClose }: { open: boolean; contact: Contact | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ContactPayload>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (open) {
      setForm(contact ? { name: contact.name, email: contact.email, company: contact.company, segment: contact.segment, subscribed: contact.subscribed } : EMPTY);
      setErrors({});
    }
  }, [open, contact]);

  const save = useMutation({
    mutationFn: () => (contact ? api.updateContact(contact.id, form) : api.createContact(form)),
    onSuccess: (saved) => {
      toast.success(contact ? "Contact updated" : "Contact added", { description: `${saved.name} · ${saved.email}` });
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
      queryClient.invalidateQueries({ queryKey: ["meta"] });
      onClose();
    },
    onError: (e: Error) => {
      if (e instanceof ApiError) setErrors(e.errors);
      toast.error("Couldn't save contact", { description: e.message });
    },
  });

  const set = <K extends keyof ContactPayload>(key: K, value: ContactPayload[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => ({ ...e, [key]: "" }));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const found: Record<string, string> = {};
    if (!form.name.trim()) found.name = "Name is required.";
    if (!/^\S+@\S+\.\S+$/.test(form.email.trim())) found.email = "Enter a valid email address.";
    setErrors(found);
    if (Object.keys(found).length === 0) save.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{contact ? "Edit contact" : "Add contact"}</DialogTitle>
          <DialogDescription>Email addresses must be unique (not case-sensitive).</DialogDescription>
        </DialogHeader>
        <form id="contact-form" noValidate onSubmit={submit} className="space-y-4">
          <div>
            <Label htmlFor="c-name">Full name</Label>
            <Input id="c-name" className="mt-1.5" value={form.name} onChange={(e) => set("name", e.target.value)} aria-invalid={!!errors.name} />
            <FieldError message={errors.name} />
          </div>
          <div>
            <Label htmlFor="c-email">Email</Label>
            <Input id="c-email" type="email" className="mt-1.5" value={form.email} onChange={(e) => set("email", e.target.value)} aria-invalid={!!errors.email} placeholder="name@company.example" />
            <FieldError message={errors.email} />
          </div>
          <div>
            <Label htmlFor="c-company">Company</Label>
            <Input id="c-company" className="mt-1.5" value={form.company} onChange={(e) => set("company", e.target.value)} aria-invalid={!!errors.company} />
            <FieldError message={errors.company} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="c-segment">Segment</Label>
              <Select value={form.segment} onValueChange={(v) => set("segment", v as Segment)}>
                <SelectTrigger id="c-segment" className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SEGMENTS.map((s) => (
                    <SelectItem key={s.value} value={s.value}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="c-sub">Subscription</Label>
              <Select value={form.subscribed ? "yes" : "no"} onValueChange={(v) => set("subscribed", v === "yes")}>
                <SelectTrigger id="c-sub" className="mt-1.5">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="yes">Subscribed</SelectItem>
                  <SelectItem value="no">Unsubscribed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="contact-form" disabled={save.isPending}>
            {save.isPending ? "Saving…" : contact ? "Save changes" : "Add contact"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function ContactsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [segment, setSegment] = useState("all");
  const [subscription, setSubscription] = useState("all");
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState<{ open: boolean; contact: Contact | null }>({ open: false, contact: null });
  const q = useDebounced(search);

  useEffect(() => setPage(1), [q, segment, subscription]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["contacts", { q, segment, subscription, page }],
    queryFn: () =>
      api.contacts({
        search: q,
        segment: segment === "all" ? undefined : segment,
        subscription: subscription === "all" ? undefined : subscription,
        page,
        page_size: PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });

  const toggle = useMutation({
    mutationFn: (c: Contact) => api.setSubscribed(c.id, !c.subscribed),
    onSuccess: (c) => {
      toast.success(c.subscribed ? "Contact subscribed" : "Contact unsubscribed", {
        description: c.subscribed ? `${c.email} will receive future campaigns.` : `${c.email} won't receive any further emails, including pending ones.`,
      });
      queryClient.invalidateQueries({ queryKey: ["contacts"] });
      queryClient.invalidateQueries({ queryKey: ["meta"] });
    },
    onError: (e: Error) => toast.error("Couldn't update subscription", { description: e.message }),
  });

  const filtered = !!q || segment !== "all" || subscription !== "all";

  return (
    <>
      <PageHeader
        title="Contacts"
        description="People who can receive your campaigns. Only subscribed contacts are included in sends."
        actions={
          <Button onClick={() => setDialog({ open: true, contact: null })}>
            <UserPlus /> Add contact
          </Button>
        }
      />
      <Card>
        <div className="flex flex-col gap-3 border-b p-4 md:flex-row md:items-center">
          <div className="relative flex-1 md:max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, email or company" className="pl-9" aria-label="Search contacts" />
          </div>
          <Select value={segment} onValueChange={setSegment}>
            <SelectTrigger className="md:w-48" aria-label="Filter by segment">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All segments</SelectItem>
              {SEGMENTS.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={subscription} onValueChange={setSubscription}>
            <SelectTrigger className="md:w-44" aria-label="Filter by subscription">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any subscription</SelectItem>
              <SelectItem value="subscribed">Subscribed</SelectItem>
              <SelectItem value="unsubscribed">Unsubscribed</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {error && !data && (
          <div className="p-4">
            <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
          </div>
        )}
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Segment</TableHead>
              <TableHead>Subscription</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="w-12">
                <span className="sr-only">Actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <TableSkeleton cols={7} rows={8} />}
            {data?.items.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="whitespace-nowrap font-medium">{c.name}</TableCell>
                <TableCell className="text-slate-600">{c.email}</TableCell>
                <TableCell className="max-w-[220px] truncate text-slate-600">{c.company || "—"}</TableCell>
                <TableCell>
                  <Badge tone={SEGMENT_TONE[c.segment]}>{SEGMENT_LABEL[c.segment]}</Badge>
                </TableCell>
                <TableCell>
                  {c.subscribed ? (
                    <Badge tone="success" icon={BellRing}>Subscribed</Badge>
                  ) : (
                    <Badge tone="muted" icon={BellOff}>Unsubscribed</Badge>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap text-slate-600">{formatDate(c.created_at)}</TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={`Actions for ${c.name}`}>
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => setDialog({ open: true, contact: c })}>
                        <Pencil /> Edit contact
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => toggle.mutate(c)}>
                        {c.subscribed ? <BellOff /> : <BellRing />} {c.subscribed ? "Unsubscribe" : "Subscribe"}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {data && data.items.length === 0 && (
          <EmptyState
            icon={Users}
            title={filtered ? "No contacts match your filters" : "No contacts yet"}
            description={filtered ? "Try a different search or filter." : "Add your first contact to start sending campaigns."}
            action={
              filtered ? (
                <Button variant="outline" onClick={() => { setSearch(""); setSegment("all"); setSubscription("all"); }}>
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        )}
        {data && data.total > 0 && <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} noun="contacts" />}
      </Card>
      <ContactDialog open={dialog.open} contact={dialog.contact} onClose={() => setDialog({ open: false, contact: null })} />
    </>
  );
}
