export type CampaignStatus = "draft" | "scheduled" | "processing" | "completed" | "cancelled";
export type RecipientStatus = "pending" | "delivered" | "failed" | "skipped";
export type JobStatus = "queued" | "processing" | "retrying" | "delivered" | "failed" | "skipped";
export type Audience = "all_subscribers" | "active_customers" | "trial_users" | "vip_customers";
export type Segment = "active_customer" | "trial_user" | "vip_customer" | "prospect";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Counts {
  pending: number;
  delivered: number;
  failed: number;
  skipped: number;
  total: number;
}

export interface Campaign {
  id: number;
  name: string;
  subject: string;
  body: string;
  audience: Audience;
  audience_label: string;
  channel: string;
  status: CampaignStatus;
  has_failures: boolean;
  status_note: string | null;
  scheduled_at: string | null;
  dispatched_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
  duplicated_from_id: number | null;
  recipient_count: number;
  recipient_count_is_estimate: boolean;
  counts: Counts;
  progress: number;
  awaiting_dispatch: boolean;
  can_edit: boolean;
  can_cancel: boolean;
  can_retry: boolean;
  has_active_run: boolean;
}

export interface DeliveryRun {
  id: number;
  run_number: number;
  kind: "initial" | "manual_retry";
  status: "active" | "finished";
  job_count: number;
  created_at: string;
  finished_at: string | null;
}

export interface CampaignDetail extends Campaign {
  runs: DeliveryRun[];
  queue_published?: boolean | null;
}

export interface Recipient {
  id: number;
  contact_id: number;
  name: string;
  email: string;
  status: RecipientStatus;
  attempt_count: number;
  last_error: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface Attempt {
  id: number;
  run_number: number;
  attempt_number: number;
  outcome: "in_progress" | "success" | "failure";
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface ActivityEvent {
  id: number;
  kind: string;
  level: "info" | "success" | "warning" | "error";
  message: string;
  campaign_id: number | null;
  campaign_name: string | null;
  created_at: string;
}

export interface Contact {
  id: number;
  name: string;
  email: string;
  company: string;
  segment: Segment;
  subscribed: boolean;
  unsubscribed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Meta {
  timezone: string;
  audiences: { value: Audience; label: string; eligible: number }[];
  segments: { value: Segment; label: string }[];
}

export interface Metric {
  value: number | null;
  definition: string;
  period_start?: string;
  delivered?: number;
  failed?: number;
}

export interface Dashboard {
  generated_at: string;
  timezone: string;
  metrics: {
    delivered_today: Metric;
    success_rate: Metric;
    pending_deliveries: Metric;
    scheduled_campaigns: Metric;
  };
  volume: { date: string; delivered: number; failed: number }[];
  status_breakdown: { status: string; label: string; count: number }[];
  recent_campaigns: Campaign[];
  next_scheduled: Campaign | null;
  activity: ActivityEvent[];
}

export interface Job {
  id: number;
  campaign_id: number;
  campaign_name: string;
  run_number: number;
  run_kind: "initial" | "manual_retry";
  recipient_id: number;
  recipient_name: string;
  recipient_email: string;
  status: JobStatus;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  next_attempt_at: string | null;
  locked_by: string | null;
  first_started_at: string | null;
  last_started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CronRun {
  id: number;
  status: "running" | "success" | "failed";
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  campaigns_dispatched: number;
  outbox_published: number;
  outbox_pending: number;
  error: string | null;
}

export interface Worker {
  worker_id: string;
  hostname: string;
  status: string;
  online: boolean;
  concurrency: number;
  jobs_processed: number;
  started_at: string;
  last_seen_at: string;
}

export interface JobSummary {
  counts: Record<JobStatus, number>;
  workers: Worker[];
  cron: {
    schedule: string;
    last_run: CronRun | null;
    last_success: CronRun | null;
    recent_runs: CronRun[];
  };
  outbox_pending: number;
  settings: {
    worker_concurrency: number;
    max_attempts: number;
    retry_delays_seconds: number[];
    sim_delay_ms: [number, number];
  };
}
