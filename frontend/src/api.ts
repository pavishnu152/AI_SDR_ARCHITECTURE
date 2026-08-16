import type { AgentLogOut, LeadOut, TokenResponse } from "./types";

// Same "no build tooling for a value that changes per environment" reasoning
// as any 12-factor app: baked in at build time via Vite's import.meta.env,
// overridable per environment without touching source. Defaults to the
// backend's local dev port (see src/main.py / uvicorn --port 8000).
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!response.ok) {
    // FastAPI's default error body is {"detail": "..."} — fall back to the
    // raw status text if the body isn't JSON (e.g. a proxy 502 page).
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // body wasn't JSON — keep statusText
    }
    throw new ApiError(response.status, detail);
  }

  // 204s and similar have no body to parse.
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  // OAuth2PasswordRequestForm on the backend expects
  // application/x-www-form-urlencoded with username/password fields, NOT
  // JSON — a common trip-up the first time you wire a frontend up to a
  // FastAPI OAuth2PasswordBearer flow.
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);

  return request<TokenResponse>("/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
}

export async function register(email: string, password: string): Promise<void> {
  await request<unknown>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function listLeads(token: string, skip = 0, limit = 50): Promise<LeadOut[]> {
  return request<LeadOut[]>(`/leads?skip=${skip}&limit=${limit}`, {}, token);
}

export function getLead(token: string, leadId: string): Promise<LeadOut> {
  return request<LeadOut>(`/leads/${leadId}`, {}, token);
}

export function getLeadLogs(token: string, leadId: string): Promise<AgentLogOut[]> {
  return request<AgentLogOut[]>(`/leads/${leadId}/logs`, {}, token);
}

export function createLead(
  token: string,
  companyName: string,
  domain?: string,
): Promise<LeadOut> {
  // This call blocks until the full 4-agent pipeline finishes (documented,
  // deliberate tradeoff in src/api/leads.py — synchronous for a
  // single-user portfolio demo, background queue is the noted next step).
  // Can take up to ~30s; the caller is responsible for showing a loading
  // state, not this function.
  return request<LeadOut>(
    "/leads",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_name: companyName, domain: domain || null }),
    },
    token,
  );
}
