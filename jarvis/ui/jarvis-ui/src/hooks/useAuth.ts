"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { getApiBaseUrl, jarvisHeaders } from "@/lib/apiBase";

const API_BASE = getApiBaseUrl();

const TOKEN_KEY = "jarvis_auth_token";

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function storeToken(token: string): void {
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Ignore if sessionStorage unavailable
  }
}

function clearStoredToken(): void {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Ignore
  }
}

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  isLocal: boolean;
  authRequired: boolean;
  token: string | null;
  loginError: string | null;
  login: (pin: string) => Promise<boolean>;
  logout: () => Promise<void>;
}

export function useAuth(): AuthState {
  const [isAuthenticated, setIsAuthenticated] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [isLocal, setIsLocal] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [token, setToken] = useState<string | null>(getStoredToken());
  const [loginError, setLoginError] = useState<string | null>(null);
  const checkedRef = useRef(false);

  const checkAuth = useCallback(async () => {
    try {
      const storedToken = getStoredToken();
      const headers = jarvisHeaders(storedToken);

      const resp = await fetch(`${API_BASE}/auth/status`, { headers });
      if (resp.ok) {
        const data = await resp.json();
        const required = data.auth_required === true;
        setAuthRequired(required);
        setIsAuthenticated(!required || data.authenticated);
        setIsLocal(data.local || false);
        if (data.authenticated && storedToken) {
          setToken(storedToken);
        }
      } else {
        setAuthRequired(true);
        setIsAuthenticated(false);
        setLoginError("JARVIS is reachable, but auth status could not be verified.");
      }
    } catch {
      setAuthRequired(true);
      setIsAuthenticated(false);
      setLoginError("Cannot reach JARVIS server. Check that the backend is running.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (checkedRef.current) return;
    checkedRef.current = true;

    checkAuth();
    const intervalId = window.setInterval(checkAuth, 5000);
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        checkAuth();
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [checkAuth]);

  const login = useCallback(async (pin: string): Promise<boolean> => {
    setLoginError(null);
    try {
      const resp = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: jarvisHeaders(null, true),
        body: JSON.stringify({ pin }),
      });

      if (resp.ok) {
        const data = await resp.json();
        const newToken = data.token || null;
        const required = data.auth_required !== false;
        setAuthRequired(required);
        setToken(newToken);
        if (newToken) {
          storeToken(newToken);
        } else {
          clearStoredToken();
        }
        setIsAuthenticated(true);
        return true;
      } else {
        const errData = await resp.json().catch(() => ({}));
        setLoginError(errData.error || "Invalid PIN.");
        return false;
      }
    } catch (err) {
      setLoginError("Cannot reach JARVIS server. Please try again.");
      return false;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      const headers = jarvisHeaders(token);
      await fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        headers,
      });
    } catch {
      // Best-effort logout
    }
    setToken(null);
    clearStoredToken();
    setIsAuthenticated(!authRequired);
  }, [authRequired, token]);

  return {
    isAuthenticated,
    isLoading,
    isLocal,
    authRequired,
    token,
    loginError,
    login,
    logout,
  };
}
