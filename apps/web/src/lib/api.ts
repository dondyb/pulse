import type {
  ActivityEvent,
  Attempt,
  Campaign,
  CampaignDetail,
  Contact,
  Dashboard,
  Job,
  JobSummary,
  Meta,
  Page,
  Recipient,
} from "./types";

export class ApiError extends Error {
  status: number;
  errors: Record<string, string>;

  constructor(status: number, message: string, errors: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

// Browser-facing API base URL, from VITE_API_BASE_URL (default: same-origin proxy).
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/+$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "Can't reach the Pulse server. Check that the API is running.");
  }
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = typeof body?.detail === "string" ? body.detail : `Request failed (${response.status})`;
    throw new ApiError(response.status, detail, body?.errors ?? {});
  }
  return body as T;
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export interface CampaignPayload {
  name: string;
  subject: string;
  body: string;
  audience: string;
  action: "draft" | "send" | "schedule";
  scheduled_at?: string | null;
}

export interface ContactPayload {
  name: string;
  email: string;
  company: string;
  segment: string;
  subscribed: boolean;
}

export const api = {
  meta: () => request<Meta>("/meta"),
  dashboard: () => request<Dashboard>("/dashboard"),

  campaigns: (p: { search?: string; status?: string; page?: number; page_size?: number }) =>
    request<Page<Campaign>>(`/campaigns${qs(p)}`),
  campaign: (id: number) => request<CampaignDetail>(`/campaigns/${id}`),
  createCampaign: (body: CampaignPayload) =>
    request<CampaignDetail>("/campaigns", { method: "POST", body: JSON.stringify(body) }),
  updateCampaign: (id: number, body: CampaignPayload) =>
    request<CampaignDetail>(`/campaigns/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  duplicateCampaign: (id: number) => request<CampaignDetail>(`/campaigns/${id}/duplicate`, { method: "POST" }),
  cancelCampaign: (id: number) => request<CampaignDetail>(`/campaigns/${id}/cancel`, { method: "POST" }),
  retryFailed: (id: number) => request<CampaignDetail>(`/campaigns/${id}/retry-failed`, { method: "POST" }),
  recipients: (id: number, p: { status?: string; search?: string; page?: number; page_size?: number }) =>
    request<Page<Recipient>>(`/campaigns/${id}/recipients${qs(p)}`),
  recipientAttempts: (id: number, recipientId: number) =>
    request<{ items: Attempt[] }>(`/campaigns/${id}/recipients/${recipientId}/attempts`),
  campaignActivity: (id: number, milestonesOnly: boolean) =>
    request<{ items: ActivityEvent[] }>(`/campaigns/${id}/activity${qs({ milestones_only: milestonesOnly, limit: 60 })}`),

  contacts: (p: { search?: string; segment?: string; subscription?: string; page?: number; page_size?: number }) =>
    request<Page<Contact>>(`/contacts${qs(p)}`),
  createContact: (body: ContactPayload) =>
    request<Contact>("/contacts", { method: "POST", body: JSON.stringify(body) }),
  updateContact: (id: number, body: ContactPayload) =>
    request<Contact>(`/contacts/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  setSubscribed: (id: number, subscribed: boolean) =>
    request<Contact>(`/contacts/${id}/${subscribed ? "subscribe" : "unsubscribe"}`, { method: "POST" }),

  jobs: (p: { status?: string; campaign_id?: number | string; search?: string; page?: number; page_size?: number }) =>
    request<Page<Job>>(`/jobs${qs(p)}`),
  jobSummary: () => request<JobSummary>("/jobs/summary"),
};
