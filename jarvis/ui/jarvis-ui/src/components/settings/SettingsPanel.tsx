"use client";

import React, { useState, useEffect, useCallback } from "react";
import { getApiBaseUrl, jarvisHeaders } from "@/lib/apiBase";

interface Settings {
  models: {
    fast: string;
    brain: string;
    deep: string;
    default: string;
  };
  costs: {
    daily_alert_usd: number;
    monthly_alert_usd: number;
    daily_hard_limit_usd: number;
    monthly_hard_limit_usd: number;
    mode: string;
    deep_premium_limit_usd: number;
  };
  cost_controls: {
    local_first_enabled: boolean;
    memory_enabled: boolean;
    privacy_mode_default: boolean;
    lazy_healthcheck: boolean;
    cache_tools: boolean;
    prompt_cache_ttl: string;
    batch_for_background: boolean;
    workflow_scheduler_enabled: boolean;
    context_recent_messages: number;
    context_summary_max_chars: number;
  };
  voice: {
    tts_engine: string;
    tts_voice: string;
    tts_speed: number;
    stt_engine: string;
  };
  integrations: {
    prefer_claude: boolean;
    ollama_url: string;
    ollama_model: string;
    ollama_fast_model: string;
  };
}

interface SystemStatus {
  anthropic: boolean;
  ollama: boolean;
  tts: string;
  stt: string;
  memory_count: number;
  uptime_seconds: number;
}

type Step = "api_keys" | "models" | "voice" | "costs";

interface SettingsPanelProps {
  authToken?: string | null;
}

function settingsApiUrl(path = ""): string {
  return `${getApiBaseUrl()}/api/settings${path}`;
}

export function SettingsPanel({ authToken }: SettingsPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState<Step>("api_keys");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [ollamaUrl, setOllamaUrl] = useState("");
  const [apiKeyValid, setApiKeyValid] = useState<boolean | null>(null);
  const [ollamaValid, setOllamaValid] = useState<boolean | null>(null);

  const loadSettings = useCallback(async () => {
    try {
      const response = await fetch(settingsApiUrl(), {
        headers: jarvisHeaders(authToken),
      });
      if (!response.ok) {
        throw new Error(`Settings request failed: ${response.status}`);
      }
      const data = await response.json();
      setSettings(data);
      setOllamaUrl(data.integrations?.ollama_url || "");
      setError(null);
    } catch (err) {
      setError("Failed to load settings");
      console.error(err);
    }
  }, [authToken]);

  const loadStatus = useCallback(async () => {
    try {
      const response = await fetch(settingsApiUrl("/status"), {
        headers: jarvisHeaders(authToken),
      });
      if (!response.ok) {
        throw new Error(`Status request failed: ${response.status}`);
      }
      const data = await response.json();
      setStatus(data);
    } catch (err) {
      console.error("Failed to load status:", err);
    }
  }, [authToken]);

  // Load settings on mount
  useEffect(() => {
    if (isOpen) {
      loadSettings();
      loadStatus();
    }
  }, [isOpen, loadSettings, loadStatus]);

  async function testApiKey() {
    if (!apiKey) {
      setError("Please enter an API key");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(settingsApiUrl("/test-api"), {
        method: "POST",
        headers: jarvisHeaders(authToken, true),
        body: JSON.stringify({ api_key: apiKey }),
      });
      const result = await response.json();

      if (result.valid) {
        setApiKeyValid(true);
        setError(null);
      } else {
        setApiKeyValid(false);
        setError(result.error || "API key is invalid");
      }
    } catch (err) {
      setApiKeyValid(false);
      setError("Failed to test API key");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function testOllama() {
    if (!ollamaUrl) {
      setError("Please enter Ollama URL");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(settingsApiUrl("/test-ollama"), {
        method: "POST",
        headers: jarvisHeaders(authToken, true),
        body: JSON.stringify({ base_url: ollamaUrl }),
      });
      const result = await response.json();

      if (result.valid) {
        setOllamaValid(true);
        setError(null);
      } else {
        setOllamaValid(false);
        setError(result.error || "Ollama is not reachable");
      }
    } catch (err) {
      setOllamaValid(false);
      setError("Failed to test Ollama");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function saveSettings(updates: Record<string, any>) {
    setLoading(true);
    try {
      const response = await fetch(settingsApiUrl("/update"), {
        method: "POST",
        headers: jarvisHeaders(authToken, true),
        body: JSON.stringify(updates),
      });

      if (!response.ok) {
        throw new Error("Failed to save settings");
      }

      const result = await response.json();
      if (result.success) {
        setError(null);
        await loadSettings();
      } else {
        setError(result.error || "Failed to save settings");
      }
    } catch (err) {
      setError("Failed to save settings");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  const isSmallScreen = typeof window !== "undefined" && window.innerWidth < 768;

  return (
    <>
      {/* Settings Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-6 right-6 w-12 h-12 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 text-white shadow-lg hover:shadow-xl transition-all duration-200 flex items-center justify-center z-40 backdrop-blur-sm"
        title="Settings"
      >
        <svg
          className="w-6 h-6"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
          />
        </svg>
      </button>

      {/* Panel Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Sliding Panel */}
      <div
        className={`fixed top-0 right-0 h-full w-full md:w-96 bg-gradient-to-b from-slate-900 to-slate-800 shadow-2xl z-50 transform transition-transform duration-300 ease-out overflow-y-auto ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Panel Header */}
        <div className="sticky top-0 bg-gradient-to-b from-slate-900/95 to-slate-800/95 backdrop-blur-md border-b border-slate-700 p-4 flex justify-between items-center">
          <h2 className="text-xl font-bold text-white">JARVIS Settings</h2>
          <button
            onClick={() => setIsOpen(false)}
            className="text-slate-400 hover:text-white transition"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mx-4 mt-4 p-3 bg-red-900/30 border border-red-700 rounded text-red-200 text-sm">
            {error}
          </div>
        )}

        {/* Content */}
        <div className="p-4 space-y-6">
          {/* Step Indicator */}
          <div className="flex gap-2">
            <button
              onClick={() => setCurrentStep("api_keys")}
              className={`flex-1 py-2 px-3 rounded text-xs font-semibold transition ${
                currentStep === "api_keys"
                  ? "bg-blue-600 text-white"
                  : "bg-slate-700 text-slate-300 hover:bg-slate-600"
              }`}
            >
              API
            </button>
            <button
              onClick={() => setCurrentStep("models")}
              className={`flex-1 py-2 px-3 rounded text-xs font-semibold transition ${
                currentStep === "models"
                  ? "bg-blue-600 text-white"
                  : "bg-slate-700 text-slate-300 hover:bg-slate-600"
              }`}
            >
              Models
            </button>
            <button
              onClick={() => setCurrentStep("voice")}
              className={`flex-1 py-2 px-3 rounded text-xs font-semibold transition ${
                currentStep === "voice"
                  ? "bg-blue-600 text-white"
                  : "bg-slate-700 text-slate-300 hover:bg-slate-600"
              }`}
            >
              Voice
            </button>
            <button
              onClick={() => setCurrentStep("costs")}
              className={`flex-1 py-2 px-3 rounded text-xs font-semibold transition ${
                currentStep === "costs"
                  ? "bg-blue-600 text-white"
                  : "bg-slate-700 text-slate-300 hover:bg-slate-600"
              }`}
            >
              Costs
            </button>
          </div>

          {/* Step 1: API Keys */}
          {currentStep === "api_keys" && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-slate-300 mb-2">
                  Anthropic API Key
                </label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition"
                />
                <button
                  onClick={testApiKey}
                  disabled={loading}
                  className="mt-2 w-full py-2 px-3 bg-blue-600 hover:bg-blue-700 text-white rounded font-semibold transition disabled:opacity-50"
                >
                  {loading ? "Testing..." : "Test API"}
                </button>
                {apiKeyValid === true && (
                  <p className="mt-2 text-green-400 text-sm">API key is valid</p>
                )}
                {apiKeyValid === false && (
                  <p className="mt-2 text-red-400 text-sm">API key is invalid</p>
                )}
                <button
                  onClick={() => saveSettings({ ANTHROPIC_API_KEY: apiKey })}
                  disabled={loading || !apiKey}
                  className="mt-2 w-full py-2 px-3 bg-slate-700 hover:bg-slate-600 text-white rounded font-semibold transition disabled:opacity-50"
                >
                  Save API Key
                </button>
              </div>

              <div>
                <label className="block text-sm font-semibold text-slate-300 mb-2">
                  Ollama URL
                </label>
                <input
                  type="text"
                  value={ollamaUrl}
                  onChange={(e) => setOllamaUrl(e.target.value)}
                  placeholder="http://localhost:11434"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition"
                />
                <button
                  onClick={testOllama}
                  disabled={loading}
                  className="mt-2 w-full py-2 px-3 bg-blue-600 hover:bg-blue-700 text-white rounded font-semibold transition disabled:opacity-50"
                >
                  {loading ? "Testing..." : "Test Ollama"}
                </button>
                {ollamaValid === true && (
                  <p className="mt-2 text-green-400 text-sm">Ollama is reachable</p>
                )}
                {ollamaValid === false && (
                  <p className="mt-2 text-red-400 text-sm">Ollama is not reachable</p>
                )}
                <button
                  onClick={() => saveSettings({ OLLAMA_BASE_URL: ollamaUrl })}
                  disabled={loading || !ollamaUrl}
                  className="mt-2 w-full py-2 px-3 bg-slate-700 hover:bg-slate-600 text-white rounded font-semibold transition disabled:opacity-50"
                >
                  Save Ollama URL
                </button>
              </div>

              {/* Status Indicators */}
              {status && (
                <div className="mt-6 p-3 bg-slate-700/50 rounded space-y-2">
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        status.anthropic ? "bg-green-500" : "bg-red-500"
                      }`}
                    />
                    <span className="text-sm text-slate-300">
                      Anthropic: {status.anthropic ? "Connected" : "Disconnected"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-2 h-2 rounded-full ${
                        status.ollama ? "bg-green-500" : "bg-red-500"
                      }`}
                    />
                    <span className="text-sm text-slate-300">
                      Ollama: {status.ollama ? "Connected" : "Disconnected"}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Step 2: Models */}
          {currentStep === "models" && settings && (
            <div className="space-y-3">
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Fast Model
                </label>
                <p className="text-xs text-slate-400">{settings.models.fast}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Brain Model
                </label>
                <p className="text-xs text-slate-400">{settings.models.brain}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Deep Model
                </label>
                <p className="text-xs text-slate-400">{settings.models.deep}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Default Tier
                </label>
                <select
                  defaultValue={settings.models.default}
                  onChange={(e) => saveSettings({ CLAUDE_DEFAULT_TIER: e.target.value })}
                  className="mt-1 w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="fast">Fast (Haiku)</option>
                  <option value="brain">Brain (Sonnet)</option>
                  <option value="deep">Deep (Opus)</option>
                </select>
              </div>
            </div>
          )}

          {/* Step 3: Voice */}
          {currentStep === "voice" && settings && (
            <div className="space-y-3">
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  TTS Engine
                </label>
                <p className="text-xs text-slate-400">{settings.voice.tts_engine}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Voice
                </label>
                <p className="text-xs text-slate-400">{settings.voice.tts_voice}</p>
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Speech Speed
                </label>
                <input
                  type="number"
                  min="0.5"
                  max="2.0"
                  step="0.05"
                  defaultValue={settings.voice.tts_speed}
                  onChange={(e) => saveSettings({ TTS_SPEED: parseFloat(e.target.value) })}
                  className="mt-1 w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  STT Engine
                </label>
                <p className="text-xs text-slate-400">{settings.voice.stt_engine}</p>
              </div>
            </div>
          )}

          {/* Step 4: Costs */}
          {currentStep === "costs" && settings && (
            <div className="space-y-3">
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Cost Mode
                </label>
                <select
                  defaultValue={settings.costs.mode}
                  onChange={(e) => saveSettings({ COST_MODE: e.target.value })}
                  className="mt-1 w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="economy">Economy</option>
                  <option value="balanced">Balanced</option>
                  <option value="power">Power</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Daily Alert Threshold (USD)
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  defaultValue={settings.costs.daily_alert_usd}
                  onChange={(e) => saveSettings({ COST_DAILY_ALERT: parseFloat(e.target.value) })}
                  className="mt-1 w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Daily Hard Limit (USD)
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  defaultValue={settings.costs.daily_hard_limit_usd}
                  onChange={(e) => saveSettings({ COST_DAILY_HARD_LIMIT: parseFloat(e.target.value) })}
                  className="mt-1 w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Monthly Alert Threshold (USD)
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  defaultValue={settings.costs.monthly_alert_usd}
                  onChange={(e) => saveSettings({ COST_MONTHLY_ALERT: parseFloat(e.target.value) })}
                  className="mt-1 w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Monthly Hard Limit (USD)
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  defaultValue={settings.costs.monthly_hard_limit_usd}
                  onChange={(e) => saveSettings({ COST_MONTHLY_HARD_LIMIT: parseFloat(e.target.value) })}
                  className="mt-1 w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="text-sm font-semibold text-slate-300">
                  Prompt Cache TTL
                </label>
                <select
                  defaultValue={settings.cost_controls.prompt_cache_ttl}
                  onChange={(e) => saveSettings({ ANTHROPIC_PROMPT_CACHE_TTL: e.target.value })}
                  className="mt-1 w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="5m">5 minutes</option>
                  <option value="1h">1 hour</option>
                </select>
              </div>
              <ToggleRow
                label="Local-first routing"
                checked={settings.cost_controls.local_first_enabled}
                onChange={(checked) => saveSettings({ LOCAL_FIRST_ENABLED: checked })}
              />
              <ToggleRow
                label="Memory storage"
                checked={settings.cost_controls.memory_enabled}
                onChange={(checked) => saveSettings({ MEMORY_ENABLED: checked })}
              />
              <ToggleRow
                label="Privacy by default"
                checked={settings.cost_controls.privacy_mode_default}
                onChange={(checked) => saveSettings({ PRIVACY_MODE_DEFAULT: checked })}
              />
              <ToggleRow
                label="Cache tool schemas"
                checked={settings.cost_controls.cache_tools}
                onChange={(checked) => saveSettings({ ANTHROPIC_CACHE_TOOLS: checked })}
              />
              <ToggleRow
                label="Lazy Claude healthcheck"
                checked={settings.cost_controls.lazy_healthcheck}
                onChange={(checked) => saveSettings({ ANTHROPIC_LAZY_HEALTHCHECK: checked })}
              />
              <ToggleRow
                label="Workflow scheduler"
                checked={settings.cost_controls.workflow_scheduler_enabled}
                onChange={(checked) => saveSettings({ WORKFLOW_SCHEDULER_ENABLED: checked })}
              />
            </div>
          )}

          {/* System Info */}
          {status && (
            <div className="mt-6 p-3 bg-slate-700/50 rounded border border-slate-600 space-y-2 text-xs text-slate-400">
              <div>Memory entries: {status.memory_count}</div>
              <div>Uptime: {Math.floor(status.uptime_seconds / 60)}m</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-3 rounded border border-slate-700 bg-slate-800/50 px-3 py-2">
      <span className="text-sm font-semibold text-slate-300">{label}</span>
      <input
        type="checkbox"
        defaultChecked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 accent-blue-500"
      />
    </label>
  );
}
