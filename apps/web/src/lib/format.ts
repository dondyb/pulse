// All dates display in the business timezone (Asia/Jakarta, UTC+7, no DST).
// Timestamps from the API are UTC ISO-8601 strings.
export const DISPLAY_TZ = "Asia/Jakarta";
export const TZ_LABEL = "WIB (Asia/Jakarta, UTC+7)";
const TZ_OFFSET = "+07:00";

const dateTimeFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: DISPLAY_TZ,
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dateFmt = new Intl.DateTimeFormat("en-GB", { timeZone: DISPLAY_TZ, day: "numeric", month: "short", year: "numeric" });
const timeFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: DISPLAY_TZ,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const partsFmt = new Intl.DateTimeFormat("en-CA", {
  timeZone: DISPLAY_TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return `${dateTimeFmt.format(new Date(iso))} WIB`;
}

const shortDateTimeFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: DISPLAY_TZ,
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** Compact form for tables, e.g. "19 Oct, 12:38". */
export function formatShortDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return shortDateTimeFmt.format(new Date(iso));
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateFmt.format(new Date(iso));
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return timeFmt.format(new Date(iso));
}

export function formatRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const diff = Math.round((new Date(iso).getTime() - now) / 1000);
  const abs = Math.abs(diff);
  const future = diff > 0;
  let text: string;
  if (abs < 5) return future ? "in a moment" : "just now";
  if (abs < 60) text = `${abs}s`;
  else if (abs < 3600) text = `${Math.floor(abs / 60)}m`;
  else if (abs < 86400) text = `${Math.floor(abs / 3600)}h`;
  else text = `${Math.floor(abs / 86400)}d`;
  return future ? `in ${text}` : `${text} ago`;
}

/** Value for <input type="datetime-local"> in Jakarta time. */
export function toJakartaInput(date: Date): string {
  const p = Object.fromEntries(partsFmt.formatToParts(date).map((x) => [x.type, x.value]));
  const hour = p.hour === "24" ? "00" : p.hour;
  return `${p.year}-${p.month}-${p.day}T${hour}:${p.minute}`;
}

/** Interpret a datetime-local value as Jakarta time and return a UTC-offset ISO string. */
export function jakartaInputToIso(value: string): string | null {
  if (!value) return null;
  const date = new Date(`${value}:00${TZ_OFFSET}`);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function formatNumber(n: number | null | undefined): string {
  return n === null || n === undefined ? "—" : new Intl.NumberFormat("en-US").format(n);
}

export function formatPercent(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined) return "—";
  return `${(ratio * 100).toFixed(digits)}%`;
}

export function shortDay(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}
