// Mirrors src/schemas/lead.py and src/schemas/auth.py on the backend.
// Kept as a hand-written mirror rather than codegen (e.g. openapi-typescript)
// for now — see Future Improvements in docs/architecture.md. The tradeoff:
// this file can silently drift from the backend if a field is renamed there
// and not here. Acceptable for a single-developer portfolio project; not
// something to carry into a real team codebase without generating it.

export type LeadStatus =
  | "pending"
  | "researched"
  | "scored"
  | "drafted"
  | "guardrail_flagged"
  | "ready"
  | "rejected"
  | "failed";

export interface Signal {
  label: string;
  detail: string;
  source_url: string | null;
}

export interface LeadProfileOut {
  lead_id: string;
  summary: string;
  signals: Signal[];
  sources: string[];
  created_at: string;
}

export interface ScoreResultOut {
  lead_id: string;
  score: number;
  confidence: number;
  reasoning: string;
  created_at: string;
}

export interface OutreachDraftOut {
  lead_id: string;
  channel: string;
  message: string;
  guardrail_approved: boolean;
  guardrail_notes: string | null;
  created_at: string;
}

export interface LeadOut {
  id: string;
  company_name: string;
  domain: string | null;
  status: LeadStatus;
  created_at: string;
  profile: LeadProfileOut | null;
  score: ScoreResultOut | null;
  draft: OutreachDraftOut | null;
}

export interface AgentLogOut {
  agent_name: string;
  model_used: string;
  input_summary: string;
  output_summary: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  success: boolean;
  error: string | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}
