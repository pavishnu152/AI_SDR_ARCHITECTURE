import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { createLead, listLeads, ApiError } from "../api";
import type { LeadOut } from "../types";
import { StatusBadge } from "../components/StatusBadge";

export function LeadsPage() {
  const { token, logout } = useAuth();
  const navigate = useNavigate();
  const [leads, setLeads] = useState<LeadOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [companyName, setCompanyName] = useState("");
  const [domain, setDomain] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function refresh() {
    if (!token) return;
    setLoading(true);
    setLoadError(null);
    try {
      setLeads(await listLeads(token));
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Failed to load leads");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!token || !companyName.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const lead = await createLead(token, companyName.trim(), domain.trim() || undefined);
      setCompanyName("");
      setDomain("");
      await refresh();
      navigate(`/leads/${lead.id}`);
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "Failed to create lead");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Leads</h1>
        <button className="btn btn-ghost" onClick={logout}>
          Log out
        </button>
      </header>

      <section className="card">
        <h2>Research a new lead</h2>
        <p className="muted">
          Runs the full 4-agent pipeline synchronously (research → score → draft → guardrail
          check) — this can take up to ~30 seconds per company.
        </p>
        <form className="inline-form" onSubmit={handleCreate}>
          <input
            placeholder="Company name"
            required
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            disabled={creating}
          />
          <input
            placeholder="Domain (optional)"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            disabled={creating}
          />
          <button type="submit" className="btn btn-primary" disabled={creating}>
            {creating ? "Running pipeline..." : "Research"}
          </button>
        </form>
        {createError && <p className="error-text">{createError}</p>}
      </section>

      <section className="card">
        <div className="card-header-row">
          <h2>All leads</h2>
          <button className="btn btn-ghost" onClick={refresh} disabled={loading}>
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        {loadError && <p className="error-text">{loadError}</p>}

        {!loading && leads.length === 0 && !loadError && (
          <p className="muted">No leads yet — research one above.</p>
        )}

        {leads.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Status</th>
                <th>Score</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => (
                <tr key={lead.id}>
                  <td>
                    <Link to={`/leads/${lead.id}`}>{lead.company_name}</Link>
                  </td>
                  <td>
                    <StatusBadge status={lead.status} />
                  </td>
                  <td>{lead.score ? lead.score.score : "—"}</td>
                  <td>{new Date(lead.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
