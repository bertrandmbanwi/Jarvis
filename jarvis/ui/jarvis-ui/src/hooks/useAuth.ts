"use client";

import { useState, useEffect, useCallback, useRef } from "react";

function getApiBaseUrl(): string {
  if (typeof window === "undefined") return "http://localhost:8741";
  const port = window.location.port;
  const hostname = window.location.hostname;
  const isLocal = hostname === "localhost" || hostname === "127.0.0.1";
  if ((!port || port === "443" || port === "80") && !isLocal) {
    return `${window.location.origin}/jarvis-api`;
  }
  return `${window.location.protocol}//${hostname}:8741`;
}

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
  token: string | null;
  loginError: string | null;
  login: (pin: string) => Promise<boolean>;
  logout: () => Promise<void>;
}

export function useAuth(): AuthState {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isLocal, setIsLocal] = useState(false);
  const [token, setToken] = useState<string | null>(getStoredToken());
  const [loginError, setLoginError] = useState<string | null>(null);
  const checkedRef = useRef(false);

  useEffect(() => {
    if (checkedRef.current) return;
    checkedRef.current = true;

    const checkAuth = async () => {
      try {
        const headers: Record<string, string> = {};
        const storedToken = getStoredToken();
        if (storedToken) {
          headers["Authorization"] = `Bearer ${storedToken}`;
        }

        const resp = await fetch(`${API_BASE}/auth/status`, { headers });
        if (resp.ok) {
          const data = await resp.json();
          setIsAuthenticated(data.authenticated);
          setIsLocal(data.local || false);
          if (data.authenticated && storedToken) {
            setToken(storedToken);
          }
        }
      } catch {
        // Server not reachable; assume not authenticated
        setIsAuthenticated(false);
      } finally {
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  const login = useCallback(async (pin: string): Promise<boolean> => {
    setLoginError(null);
    try {
      const resp = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });

      if (resp.ok) {
        const data = await resp.json();
        const newToken = data.token;
        setToken(newToken);
        storeToken(newToken);
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
      const headers: Record<string, string> = {};
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }
      await fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        headers,
      });
    } catch {
      // Best-effort logout
    }
    setToken(null);
    clearStoredToken();
    setIsAuthenticated(false);
  }, [token]);

  return {
    isAuthenticated,
    isLoading,
    isLocal,
    token,
    loginError,
    login,
    logout,
  };
}
