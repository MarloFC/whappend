"use client";

import { useState, useEffect } from "react";
import {
  Key,
  Eye,
  EyeOff,
  Check,
  X,
  AlertTriangle,
  ExternalLink,
  ShieldCheck,
  Loader2,
  Users,
  Trash2,
  UserPlus,
} from "lucide-react";
import {
  getMyGroqKeyStatus,
  saveMyGroqKey,
  deleteMyGroqKey,
  listAllowedUsers,
  addAllowedUser,
  removeAllowedUser,
  type GroqKeyStatus,
} from "@/lib/api";
import type { AllowedUserItem, UserProfile } from "@/lib/types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  user: UserProfile | null;
  onKeyChange?: (hasKey: boolean, last4?: string | null) => void;
}

export default function ApiKeyModal({ isOpen, onClose, user, onKeyChange }: Props) {
  const [activeTab, setActiveTab] = useState<"key" | "allowlist">("key");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [keyStatus, setKeyStatus] = useState<GroqKeyStatus | null>(null);
  const [statusMessage, setStatusMessage] = useState<{
    type: "success" | "error" | "info";
    text: string;
  } | null>(null);
  const [isValidating, setIsValidating] = useState(false);

  // Admin allowlist state
  const [allowedUsers, setAllowedUsers] = useState<AllowedUserItem[]>([]);
  const [newPhone, setNewPhone] = useState("");
  const [newRole, setNewRole] = useState<"user" | "admin">("user");
  const [newName, setNewName] = useState("");
  const [adminLoading, setAdminLoading] = useState(false);

  useEffect(() => {
    if (isOpen && user) {
      setApiKey("");
      setStatusMessage(null);
      getMyGroqKeyStatus()
        .then(setKeyStatus)
        .catch(() => setKeyStatus({ configured: user.has_groq_key, provider: "groq", key_last4: user.groq_key_last4 }));

      if (user.role === "admin") {
        listAllowedUsers()
          .then(setAllowedUsers)
          .catch(() => {});
      }
    }
  }, [isOpen, user]);

  if (!isOpen) return null;

  const handleSaveAndTest = async () => {
    const trimmed = apiKey.trim();
    if (!trimmed) {
      setStatusMessage({ type: "error", text: "Please paste a valid Groq API key (gsk_...)." });
      return;
    }

    setIsValidating(true);
    setStatusMessage(null);
    try {
      const saved = await saveMyGroqKey(trimmed);
      setKeyStatus(saved);
      setApiKey("");
      setStatusMessage({
        type: "success",
        text: saved.message || "Groq API key verified, encrypted with Fernet, and saved to your account!",
      });
      onKeyChange?.(true, saved.key_last4);
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to validate & save key.",
      });
    } finally {
      setIsValidating(false);
    }
  };

  const handleClear = async () => {
    setIsValidating(true);
    try {
      const res = await deleteMyGroqKey();
      setKeyStatus(res);
      setApiKey("");
      setStatusMessage({
        type: "info",
        text: "Your Groq API key was deleted from the database.",
      });
      onKeyChange?.(false, null);
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Could not remove key.",
      });
    } finally {
      setIsValidating(false);
    }
  };

  const handleAddAllowedPhone = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPhone.trim()) return;
    setAdminLoading(true);
    setStatusMessage(null);
    try {
      await addAllowedUser(newPhone.trim(), newRole, newName.trim() || undefined);
      setNewPhone("");
      setNewName("");
      const updated = await listAllowedUsers();
      setAllowedUsers(updated);
      setStatusMessage({ type: "success", text: "Phone number added to allowlist." });
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to add phone number.",
      });
    } finally {
      setAdminLoading(false);
    }
  };

  const handleRemoveAllowedPhone = async (phone: string) => {
    setAdminLoading(true);
    setStatusMessage(null);
    try {
      await removeAllowedUser(phone);
      const updated = await listAllowedUsers();
      setAllowedUsers(updated);
    } catch (err) {
      setStatusMessage({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to remove phone number.",
      });
    } finally {
      setAdminLoading(false);
    }
  };

  const isConfigured = Boolean(keyStatus?.configured);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 540 }}>
        {/* Modal Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            <div className="modal-icon-badge">
              <Key size={18} />
            </div>
            <div>
              <h2 className="modal-title">BYOK Groq Key &amp; Account Settings</h2>
              <p className="modal-subtitle">
                Signed in as <code>{user?.phone_e164}</code> ({user?.role}) · Shared between Web &amp; Telegram
              </p>
            </div>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="modal-body">
          {user?.role === "admin" && (
            <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
              <button
                type="button"
                className={`btn btn-sm ${activeTab === "key" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => {
                  setActiveTab("key");
                  setStatusMessage(null);
                }}
              >
                <Key size={14} /> My Groq Key (BYOK)
              </button>
              <button
                type="button"
                className={`btn btn-sm ${activeTab === "allowlist" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => {
                  setActiveTab("allowlist");
                  setStatusMessage(null);
                }}
              >
                <Users size={14} /> Phone Allowlist ({allowedUsers.length})
              </button>
            </div>
          )}

          {activeTab === "key" ? (
            <>
              {/* Key Status Pill */}
              <div className="key-status-banner">
                <div className="key-status-indicator">
                  {isConfigured ? (
                    <>
                      <span className="status-dot status-dot--active" />
                      <span className="status-text font-medium text-emerald-400">
                        Encrypted Key Active (<code>gsk_••••{keyStatus?.key_last4}</code>)
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="status-dot status-dot--warning" />
                      <span className="status-text text-amber-400">
                        No Groq Key Set — Required to chat &amp; analyze media
                      </span>
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
                  {isConfigured ? "Replace Groq API Key" : "Groq API Key"} (starts with{" "}
                  <code>gsk_...</code>)
                </label>
                <div className="input-password-wrapper">
                  <input
                    id="groq-key-input"
                    type={showKey ? "text" : "password"}
                    placeholder={
                      isConfigured
                        ? `Current: gsk_••••••••••••••••••••${keyStatus?.key_last4}`
                        : "gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                    }
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

              {/* Security & BYOK Explanation */}
              <div className="security-notice">
                <ShieldCheck size={16} className="security-notice-icon" />
                <p className="security-notice-text">
                  <strong>Encrypted at Rest (BYOK):</strong> Your key is verified with Groq and
                  encrypted with <code>Fernet (AES-128-CBC + HMAC)</code> in the database. There is
                  no default server key, and the same key automatically powers your Telegram bot
                  sessions.
                </p>
              </div>
            </>
          ) : (
            /* Admin Allowlist Management Tab */
            <div>
              <form
                onSubmit={handleAddAllowedPhone}
                style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}
              >
                <input
                  type="tel"
                  placeholder="+5511988887777"
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  className="input-field"
                  style={{ flex: "1 1 160px" }}
                  required
                />
                <input
                  type="text"
                  placeholder="Name (optional)"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="input-field"
                  style={{ flex: "1 1 120px" }}
                />
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value as "user" | "admin")}
                  className="input-field"
                  style={{ width: 95 }}
                >
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
                <button type="submit" className="btn btn-primary btn-sm" disabled={adminLoading}>
                  <UserPlus size={14} /> Allow
                </button>
              </form>

              <div
                style={{
                  maxHeight: 220,
                  overflowY: "auto",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 8,
                  padding: 8,
                }}
              >
                {allowedUsers.map((u) => (
                  <div
                    key={u.id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "6px 8px",
                      borderBottom: "1px solid rgba(255,255,255,0.05)",
                      fontSize: "0.82rem",
                    }}
                  >
                    <div>
                      <code>{u.phone_e164}</code>{" "}
                      <span style={{ opacity: 0.7 }}>
                        [{u.role}] {u.display_name ? `· ${u.display_name}` : ""}
                      </span>
                      <div style={{ fontSize: "0.75rem", opacity: 0.65 }}>
                        {u.telegram_user_id ? `Telegram #${u.telegram_user_id}` : "Telegram unlinked"}{" "}
                        · {u.has_groq_key ? `Key ••••${u.groq_key_last4}` : "No key yet"}
                      </div>
                    </div>
                    {u.phone_e164 !== user?.phone_e164 && (
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm text-rose-400"
                        onClick={() => handleRemoveAllowedPhone(u.phone_e164)}
                        disabled={adminLoading}
                        title="Remove from allowlist"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Validation Feedback Message */}
          {statusMessage && (
            <div className={`status-feedback status-feedback--${statusMessage.type}`} style={{ marginTop: 12 }}>
              {statusMessage.type === "success" && <Check size={16} />}
              {statusMessage.type === "error" && <AlertTriangle size={16} />}
              {statusMessage.type === "info" && <ShieldCheck size={16} />}
              <span>{statusMessage.text}</span>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        {activeTab === "key" && (
          <div className="modal-footer">
            {isConfigured && (
              <button
                type="button"
                className="btn btn-ghost text-rose-400 hover:text-rose-300"
                onClick={handleClear}
                disabled={isValidating}
              >
                Remove Key
              </button>
            )}
            <div className="modal-footer-actions">
              <button type="button" className="btn btn-secondary" onClick={onClose}>
                Close
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSaveAndTest}
                disabled={isValidating || !apiKey.trim()}
              >
                {isValidating ? (
                  <>
                    <Loader2 size={16} className="animate-spin" /> Verifying…
                  </>
                ) : (
                  "Verify & Save to DB"
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
