"use client";

import { useState, useEffect, useRef } from "react";
import {
  Phone,
  ShieldCheck,
  Send,
  Loader2,
  Check,
  AlertTriangle,
  MessageSquareCode,
  Film,
  Lock,
} from "lucide-react";
import {
  requestPhoneOtp,
  verifyPhoneOtp,
  loginWithTelegramWidget,
  type TelegramWidgetUser,
} from "@/lib/api";
import type { UserProfile } from "@/lib/types";

interface Props {
  onAuthenticated: (user: UserProfile) => void;
}

declare global {
  interface Window {
    onTelegramAuthWidget?: (user: TelegramWidgetUser) => void;
  }
}

export default function AuthModal({ onAuthenticated }: Props) {
  const [tab, setTab] = useState<"otp" | "widget">("otp");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [devCodeHint, setDevCodeHint] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);

  const widgetContainerRef = useRef<HTMLDivElement>(null);
  const botUsername = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || "";

  // Mount official Telegram Login Widget script when switching to the "widget" tab
  useEffect(() => {
    if (tab !== "widget" || !botUsername || !widgetContainerRef.current) return;

    window.onTelegramAuthWidget = async (tgUser: TelegramWidgetUser) => {
      setLoading(true);
      setFeedback(null);
      try {
        const res = await loginWithTelegramWidget(tgUser);
        onAuthenticated(res.user);
      } catch (err) {
        setFeedback({
          type: "error",
          text: err instanceof Error ? err.message : "Telegram widget login failed.",
        });
      } finally {
        setLoading(false);
      }
    };

    const container = widgetContainerRef.current;
    container.innerHTML = "";
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", botUsername.replace(/^@/, ""));
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "10");
    script.setAttribute("data-onauth", "onTelegramAuthWidget(user)");
    script.setAttribute("data-request-access", "write");
    container.appendChild(script);

    return () => {
      container.innerHTML = "";
    };
  }, [tab, botUsername, onAuthenticated]);

  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phone.trim()) return;
    setLoading(true);
    setFeedback(null);
    setDevCodeHint(null);
    try {
      const res = await requestPhoneOtp(phone.trim());
      setPhone(res.phone_e164);
      setOtpSent(true);
      if (res.dev_code) {
        setDevCodeHint(res.dev_code);
        setCode(res.dev_code);
      }
      setFeedback({ type: "info", text: res.message });
    } catch (err) {
      setFeedback({
        type: "error",
        text: err instanceof Error ? err.message : "Failed to send verification code.",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!code.trim()) return;
    setLoading(true);
    setFeedback(null);
    try {
      const res = await verifyPhoneOtp(phone.trim(), code.trim());
      onAuthenticated(res.user);
    } catch (err) {
      setFeedback({
        type: "error",
        text: err instanceof Error ? err.message : "Invalid verification code.",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-dialog" style={{ maxWidth: 460 }}>
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            <div className="modal-icon-badge">
              <Lock size={18} />
            </div>
            <div>
              <h2 className="modal-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Film size={16} /> WhAppend Sign In
              </h2>
              <p className="modal-subtitle">
                Allowlisted phone numbers only · Bring Your Own Groq Key (BYOK)
              </p>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="modal-body">
          {/* Login Method Switcher */}
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <button
              type="button"
              className={`btn btn-sm ${tab === "otp" ? "btn-primary" : "btn-secondary"}`}
              style={{ flex: 1, justifyContent: "center" }}
              onClick={() => {
                setTab("otp");
                setFeedback(null);
              }}
            >
              <Phone size={14} />
              <span>Phone + Bot Code</span>
            </button>
            <button
              type="button"
              className={`btn btn-sm ${tab === "widget" ? "btn-primary" : "btn-secondary"}`}
              style={{ flex: 1, justifyContent: "center" }}
              onClick={() => {
                setTab("widget");
                setFeedback(null);
              }}
            >
              <Send size={14} />
              <span>Telegram Widget</span>
            </button>
          </div>

          {tab === "otp" ? (
            !otpSent ? (
              <form onSubmit={handleRequestOtp}>
                <div className="form-group">
                  <label className="form-label" htmlFor="phone-input">
                    Your Allowed Phone Number (E.164, e.g. <code>+5511999999999</code>)
                  </label>
                  <input
                    id="phone-input"
                    type="tel"
                    placeholder="+5511999999999"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="input-field"
                    autoFocus
                    required
                  />
                </div>
                <div style={{ marginTop: 14, display: "flex", justifyContent: "flex-end" }}>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    style={{ width: "100%", justifyContent: "center" }}
                    disabled={loading || !phone.trim()}
                  >
                    {loading ? (
                      <>
                        <Loader2 size={16} className="animate-spin" /> Sending Code…
                      </>
                    ) : (
                      <>
                        <MessageSquareCode size={16} /> Send Login Code via Telegram Bot
                      </>
                    )}
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleVerifyOtp}>
                <div className="form-group">
                  <label className="form-label" htmlFor="otp-input">
                    6-Digit Code sent to <code>{phone}</code> on Telegram
                  </label>
                  <input
                    id="otp-input"
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    placeholder="123456"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    className="input-field"
                    style={{ letterSpacing: "0.25em", fontSize: "1.1rem", textAlign: "center" }}
                    autoFocus
                    required
                  />
                </div>

                {devCodeHint && (
                  <div className="status-feedback status-feedback--info" style={{ marginTop: 10 }}>
                    <ShieldCheck size={16} />
                    <span>
                      Local dev mode (no bot token set): code pre-filled as <code>{devCodeHint}</code>
                    </span>
                  </div>
                )}

                <div style={{ marginTop: 14, display: "flex", gap: 8 }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      setOtpSent(false);
                      setCode("");
                      setFeedback(null);
                    }}
                  >
                    ← Change Phone
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    style={{ flex: 1, justifyContent: "center" }}
                    disabled={loading || code.trim().length < 6}
                  >
                    {loading ? (
                      <>
                        <Loader2 size={16} className="animate-spin" /> Verifying…
                      </>
                    ) : (
                      <>
                        <Check size={16} /> Verify &amp; Sign In
                      </>
                    )}
                  </button>
                </div>
              </form>
            )
          ) : (
            <div style={{ textAlign: "center", padding: "14px 0" }}>
              {botUsername ? (
                <>
                  <p style={{ fontSize: "0.85rem", opacity: 0.85, marginBottom: 14 }}>
                    Sign in with one click using your Telegram account linked to{" "}
                    <code>@{botUsername.replace(/^@/, "")}</code>:
                  </p>
                  <div
                    ref={widgetContainerRef}
                    style={{ display: "flex", justifyContent: "center", minHeight: 44 }}
                  />
                </>
              ) : (
                <div className="status-feedback status-feedback--info">
                  <AlertTriangle size={16} />
                  <span>
                    Set <code>NEXT_PUBLIC_TELEGRAM_BOT_USERNAME=YourBotName</code> in{" "}
                    <code>frontend/.env.local</code> to enable the one-click Telegram Login Widget, or
                    use the <strong>Phone + Bot Code</strong> tab now.
                  </span>
                </div>
              )}
            </div>
          )}

          {feedback && (
            <div className={`status-feedback status-feedback--${feedback.type}`} style={{ marginTop: 12 }}>
              {feedback.type === "success" && <Check size={16} />}
              {feedback.type === "error" && <AlertTriangle size={16} />}
              {feedback.type === "info" && <ShieldCheck size={16} />}
              <span>{feedback.text}</span>
            </div>
          )}

          <div className="security-notice" style={{ marginTop: 14 }}>
            <ShieldCheck size={16} className="security-notice-icon" />
            <p className="security-notice-text">
              <strong>First time on Telegram?</strong> Open the WhAppend bot on Telegram, send{" "}
              <code>/start</code>, and tap <em>&ldquo;Share my phone number&rdquo;</em> to link your
              allowlisted number.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

