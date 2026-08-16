import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../auth";
import { getLead, getLeadLogs, ApiError } from "../api";
import type { AgentLogOut, LeadOut } from "../types";
import { StatusBadge } from "../components/StatusBadge";

export function LeadDetailPage() {
  const { leadId } = useParams<{ leadId: string }>();
  const { token } = useAuth();
  const [lead, setLead] = useState<LeadOut | null>(null);
  const [logs, setLogs] = useState<AgentLogOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !leadId) return;
    setLoading(true);
    setError(null);
    Promise.all([getLead(token, leadId), getLeadLogs(token, leadId)])
      .then(([leadData, logsData]) => {
        setLead(leadData);
        setLogs(logsData);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load lead"))
      .finally(() => setLoading(false));
  }, [token, leadId]);

  if (loading) return <div className="page">Loading...</div>;
  if (error) return <div className="page error-text">{error}</div>;
  if (!lead) return null;

  const totalCost = logs.reduce((sum, log) => sum + (log.cost_usd ?? 0), 0);
  const totalLatency = logs.reduce((sum, log) => sum + log.latency_ms, 0);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <Link to="/leads" className="back-link">
            ← All leads
          </Link>
          <h1>{lead.company_name}</h1>
        </div>
        <StatusBadge status={lead.status} />
      </header>

      <section className="card">
        <h2>Research</h2>
        {lead.profile ? (
          <>
            <p>{lead.profile.summary}</p>
            <h3>Signals</h3>
            <ul className="signal-list">
              {lead.profile.signals.map((s, i) => (
                <li key={i}>
                  <strong>{s.label}</strong>: {s.detail}
                  {s.source_url && (
                    <>
                      {" "}
                      (
                      <a href={s.source_url} target="_blank" rel="noreferrer">
                        source
                      </a>
                      )
                    </>
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="muted">No research completed for this lead.</p>
        )}
      </section>

      <section className="card">
        <h2>Score</h2>
        {lead.score ? (
          <>
            <p className="score-line">
              <span className="score-number">{lead.score.score}</span> / 100
              <span className="muted"> (confidence {(lead.score.confidence * 100).toFixed(0)}%)</span>
            </p>
            <p>{lead.score.reasoning}</p>
          </>
        ) : (
          <p className="muted">Not scored — pipeline stopped before or during scoring.</p>
        )}
      </section>

      <section className="card">
        <h2>Outreach draft</h2>
        {lead.draft ? (
          <>
            <p>
              Channel: <strong>{lead.draft.channel}</strong> —{" "}
              {lead.draft.guardrail_approved ? (
                <span className="badge badge-success">guardrail approved</span>
              ) : (
                <span className="badge badge-warning">guardrail flagged</span>
              )}
            </p>
            <pre className="draft-message">{lead.draft.message}</pre>
            {lead.draft.guardrail_notes && (
              <p className="muted">Guardrail notes: {lead.draft.guardrail_notes}</p>
            )}
          </>
        ) : (
          <p className="muted">No draft — lead was rejected, failed, or hasn't reached drafting.</p>
        )}
      </section>

      <section className="card">
        <div className="card-header-row">
          <h2>Agent trace</h2>
          <span className="muted">
            {logs.length} invocation{logs.length === 1 ? "" : "s"} · {totalLatency}ms total
            {totalCost > 0 && ` · $${totalCost.toFixed(4)}`}
          </span>
        </div>
        {logs.length === 0 ? (
          <p className="muted">No agent invocations recorded yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Agent</th>
                <th>Model</th>
                <th>Result</th>
                <th>Latency</th>
                <th>Tokens (in/out)</th>
                <th>Cost</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log, i) => (
                <tr key={i} className={log.success ? "" : "row-failed"}>
                  <td>{log.agent_name}</td>
                  <td>{log.model_used}</td>
                  <td>
                    {log.success ? (
                      <span className="badge badge-success">ok</span>
                    ) : (
                      <span className="badge badge-danger" title={log.error ?? undefined}>
                        failed
                      </span>
                    )}
                  </td>
                  <td>{log.latency_ms}ms</td>
                  <td>
                    {log.input_tokens}/{log.output_tokens}
                  </td>
                  <td>{log.cost_usd != null ? `$${log.cost_usd.toFixed(4)}` : "—"}</td>
                  <td>{new Date(log.created_at).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
