import type { LeadStatus } from "../types";

const STATUS_STYLES: Record<LeadStatus, string> = {
  pending: "badge badge-neutral",
  researched: "badge badge-neutral",
  scored: "badge badge-neutral",
  drafted: "badge badge-neutral",
  guardrail_flagged: "badge badge-warning",
  ready: "badge badge-success",
  rejected: "badge badge-muted",
  failed: "badge badge-danger",
};

export function StatusBadge({ status }: { status: LeadStatus }) {
  return <span className={STATUS_STYLES[status] ?? "badge badge-neutral"}>{status}</span>;
}
