import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { login as apiLogin } from "./api";

interface AuthContextValue {
  token: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const STORAGE_KEY = "ai_sdr_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  // KNOWN TRADEOFF, not an oversight: storing the JWT in localStorage is
  // vulnerable to XSS (any script that runs on this page can read it),
  // whereas an httpOnly cookie set by the server can't be read by client
  // JS at all. The proper production fix is the backend setting an
  // httpOnly, Secure, SameSite cookie on login instead of returning the
  // token in a JSON body — deferred here because it requires a CORS/cookie
  // rework on the FastAPI side for a single-developer local demo. Noted in
  // docs/architecture.md's Future Improvements.
  const [token, setToken] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_KEY),
  );

  useEffect(() => {
    if (token) localStorage.setItem(STORAGE_KEY, token);
    else localStorage.removeItem(STORAGE_KEY);
  }, [token]);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      isAuthenticated: token !== null,
      login: async (email: string, password: string) => {
        const { access_token } = await apiLogin(email, password);
        setToken(access_token);
      },
      logout: () => setToken(null),
    }),
    [token],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
