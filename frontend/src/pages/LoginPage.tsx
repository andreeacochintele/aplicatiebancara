import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";

type AuthMode = "login" | "register";

const NAME_PATTERN = /^\p{L}+(?:[ '-]\p{L}+)*$/u;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_PATTERN = /^\+[1-9]\d{7,14}$/;

export function LoginPage() {
  const { t } = useTranslation();
  const { login, register } = useAuth();

  function validateName(value: string, label: string): string | null {
    const trimmed = value.trim();
    if (trimmed.length < 2 || trimmed.length > 50) {
      return t("auth.nameLengthError", { label });
    }
    if (!NAME_PATTERN.test(trimmed)) {
      return t("auth.nameLettersError", { label });
    }
    return null;
  }

  function validatePassword(value: string): string | null {
    if (value.length < 8) return t("auth.passwordTooShort");
    if (!/[a-z]/.test(value)) return t("auth.passwordNeedsLowercase");
    if (!/[A-Z]/.test(value)) return t("auth.passwordNeedsUppercase");
    if (!/\d/.test(value)) return t("auth.passwordNeedsDigit");
    if (!/[^\w\s]/.test(value)) return t("auth.passwordNeedsSpecial");
    return null;
  }
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const referralCodeFromLink = searchParams.get("ref") ?? "";
  const [mode, setMode] = useState<AuthMode>(referralCodeFromLink ? "register" : "login");
  const [email, setEmail] = useState("user@example.com");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [referralCode, setReferralCode] = useState(referralCodeFromLink);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const response = await login(email, password);
      navigate(response.user.role === "ADMIN" ? "/admin" : "/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("auth.loginFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRegister(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const nameError = validateName(firstName, t("auth.firstName")) ?? validateName(lastName, t("auth.lastName"));
    if (nameError) {
      setError(nameError);
      return;
    }
    if (!EMAIL_PATTERN.test(email.trim())) {
      setError(t("auth.invalidEmail"));
      return;
    }
    if (!PHONE_PATTERN.test(phone.trim())) {
      setError(t("auth.invalidPhone"));
      return;
    }
    const passwordError = validatePassword(password);
    if (passwordError) {
      setError(passwordError);
      return;
    }
    if (password !== confirmPassword) {
      setError(t("auth.passwordsDoNotMatch"));
      return;
    }

    setSubmitting(true);
    try {
      await register({
        first_name: firstName,
        last_name: lastName,
        email,
        phone,
        password,
        referral_code: referralCode.trim() || undefined,
      });
      navigate("/onboarding");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("auth.couldNotCreateAccount"));
    } finally {
      setSubmitting(false);
    }
  }

  if (mode === "register") {
    return (
      <form onSubmit={handleRegister} className="auth-form">
        <div className="auth-form__header">
          <span className="eyebrow">{t("auth.step1")}</span>
          <h2>{t("auth.createAccount")}</h2>
        </div>
        <div className="auth-form__grid">
          <label>
            {t("auth.firstName")}
            <input
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              required
              minLength={2}
              maxLength={50}
              autoComplete="given-name"
            />
          </label>
          <label>
            {t("auth.lastName")}
            <input
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              required
              minLength={2}
              maxLength={50}
              autoComplete="family-name"
            />
          </label>
        </div>
        <label>
          {t("auth.email")}
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </label>
        <label>
          {t("auth.phone")}
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            required
            placeholder="+40712345678"
            autoComplete="tel"
          />
        </label>
        <label>
          {t("auth.password")}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
          <small className="auth-field-hint">{t("auth.passwordHint")}</small>
        </label>
        <label>
          {t("auth.confirmPassword")}
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            autoComplete="new-password"
          />
        </label>
        <label>
          {t("auth.referralCode")}
          <input
            value={referralCode}
            onChange={(e) => setReferralCode(e.target.value)}
            placeholder="EASYB-XXXXXXXX"
            maxLength={20}
          />
          <small className="auth-field-hint">{t("auth.referralHint")}</small>
        </label>
        {error && (
          <p role="alert" className="status-line status-line--error">
            {error}
          </p>
        )}
        <button type="submit" disabled={submitting}>
          {submitting ? t("auth.creatingAccount") : t("auth.createAccount")}
        </button>
        <p className="auth-switch">
          {t("auth.alreadyHaveAccount")}{" "}
          <button type="button" className="button-link" onClick={() => setMode("login")}>
            {t("auth.signIn")}
          </button>
        </p>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="auth-form">
      <label>
        {t("auth.email")}
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      <label>
        {t("auth.password")}
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? t("auth.signingIn") : t("auth.signIn")}
      </button>
      <p className="auth-switch">
        {t("auth.dontHaveAccount")}{" "}
        <button type="button" className="button-link" onClick={() => setMode("register")}>
          {t("auth.createAccount")}
        </button>
      </p>
    </form>
  );
}
