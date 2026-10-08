"use client";

import { useState, useEffect } from "react";
import { Key, Eye, EyeOff, Check, X, AlertTriangle, ExternalLink, ShieldCheck, Loader2 } from "lucide-react";
import {
  getStoredApiKey,
  setStoredApiKey,
  clearStoredApiKey,
  validateApiKey,
  getKeyStatus,
  type KeyStatusResponse,
} from "@/lib/api";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onKeyChange?: (hasKey: boolean) => void;
}

export default function ApiKeyModal({ isOpen, onClose, onKeyChange }: Props) {
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [serverStatus, setServerStatus] = useState<KeyStatusResponse | null>(null);

  useEffect(() => {
    if (isOpen) {
      const stored = getStoredApiKey();
      setApiKey(stored);
      setStatusMessage(null);
      getKeyStatus().then(setServerStatus);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSaveAndTest = async () => {
    const trimmed = apiKey.trim();
    if (!trimmed) {
      clearStoredApiKey();
      setStatusMessage({ type: "info", text: "Custom API key removed. Using server default if available." });
      onKeyChange?.(false);
      return;
    }

    setIsValidating(true);
    setStatusMessage(null);

    const res = await validateApiKey(trimmed);
    setIsValidating(false);

    if (res.valid) {
      setStoredApiKey(trimmed);
      setStatusMessage({ type: "success", text: res.message || "Key successfully verified & saved!" });
      onKeyChange?.(true);
    } else {
      setStatusMessage({ type: "error", text: res.error || "Invalid Groq API key. Please check and try again." });
    }
  };

  const handleClear = () => {
    clearStoredApiKey();
    setApiKey("");
    setStatusMessage({ type: "info", text: "Key cleared. Using server configuration." });
    onKeyChange?.(false);
  };

  const hasCustomKey = Boolean(getStoredApiKey());

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            <div className="modal-icon-badge">
              <Key size={18} />
            </div>
            <div>
              <h2 className="modal-title">Groq API Key Settings</h2>
              <p className="modal-subtitle">Bring Your Own Key (BYOK) for independent quota</p>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body">
          {/* Key Status Pill */}
          <div className="key-status-banner">
            <div className="key-status-indicator">
              {hasCustomKey ? (
                <>
                  <span className="status-dot status-dot--active" />
                  <span className="status-text font-medium text-emerald-400">Custom API Key Active</span>
                </>
              ) : serverStatus?.has_server_key ? (
                <>
                  <span className="status-dot status-dot--server" />
                  <span className="status-text">Server Default Key Active</span>
                </>
              ) : (
                <>
                  <span className="status-dot status-dot--warning" />
                  <span className="status-text text-amber-400">No Key Configured (OpenCV fallback only)</span>
                </>
              )}
            </div>
            <a
              href="https://console.groq.com/keys"
              target="_blank"
              rel="noreferrer"
              className="key-console-link"
            >
              Get Free Key <ExternalLink size={12} />
            </a>
          </div>

          {/* Input Group */}
          <div className="form-group">
            <label className="form-label" htmlFor="groq-key-input">
              Groq API Key (starts with <code>gsk_...</code>)
            </label>
            <div className="input-password-wrapper">
              <input
                id="groq-key-input"
                type={showKey ? "text" : "password"}
                placeholder="gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="input-field"
                autoComplete="off"
                spellCheck="false"
              />
              <button
                type="button"
                className="input-eye-btn"
                onClick={() => setShowKey(!showKey)}
                title={showKey ? "Hide key" : "Show key"}
              >
                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* Validation Feedback Message */}
          {statusMessage && (
            <div className={`status-feedback status-feedback--${statusMessage.type}`}>
              {statusMessage.type === "success" && <Check size={16} />}
              {statusMessage.type === "error" && <AlertTriangle size={16} />}
              {statusMessage.type === "info" && <ShieldCheck size={16} />}
              <span>{statusMessage.text}</span>
            </div>
          )}

          {/* Security & BYOK Explanation */}
          <div className="security-notice">
            <ShieldCheck size={16} className="security-notice-icon" />
            <p className="security-notice-text">
              <strong>Client Security:</strong> Your key is stored in your browser&apos;s <code>localStorage</code>. It is sent via <code>X-Groq-Api-Key</code> headers directly to the backend for your analysis requests, and is never logged or saved to the server database.
            </p>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="modal-footer">
          {hasCustomKey && (
            <button
              type="button"
              className="btn btn-ghost text-rose-400 hover:text-rose-300"
              onClick={handleClear}
            >
              Remove Custom Key
            </button>
          )}
          <div className="modal-footer-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSaveAndTest}
              disabled={isValidating}
            >
              {isValidating ? (
                <>
                  <Loader2 size={16} className="animate-spin" /> Verifying…
                </>
              ) : (
                "Save & Validate"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
