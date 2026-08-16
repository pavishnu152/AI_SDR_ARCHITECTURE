import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { register, ApiError } from "../api";

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") {
        await register(email, password);
      }
      await login(email, password);
      navigate("/leads");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="centered-page">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <h1>AI SDR</h1>
        <p className="muted">Multi-agent lead research &amp; qualification dashboard</p>

        <div className="tab-row">
          <button
            type="button"
            className={mode === "login" ? "tab active" : "tab"}
            onClick={() => setMode("login")}
          >
            Log in
          </button>
          <button
            type="button"
            className={mode === "register" ? "tab active" : "tab"}
            onClick={() => setMode("register")}
          >
            Register
          </button>
        </div>

        <label>
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
          />
        </label>

        <label>
          Password
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        </label>

        {error && <p className="error-text">{error}</p>}

        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Working..." : mode === "login" ? "Log in" : "Create account & log in"}
        </button>
      </form>
    </div>
  );
}
