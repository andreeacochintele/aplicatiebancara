import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";

type AuthMode = "login" | "register";

const NAME_PATTERN = /^\p{L}+(?:[ '-]\p{L}+)*$/u;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_PATTERN = /^\+[1-9]\d{7,14}$/;

function validateName(value: string, label: string): string | null {
  const trimmed = value.trim();
  if (trimmed.length < 2 || trimmed.length > 50) {
    return `${label} must be between 2 and 50 characters`;
  }
  if (!NAME_PATTERN.test(trimmed)) {
    return `${label} must contain only letters`;
  }
  return null;
}

function validatePassword(value: string): string | null {
  if (value.length < 8) return "Password must be at least 8 characters long";
  if (!/[a-z]/.test(value)) return "Password must contain at least one lowercase letter";
  if (!/[A-Z]/.test(value)) return "Password must contain at least one uppercase letter";
  if (!/\d/.test(value)) return "Password must contain at least one digit";
  if (!/[^\w\s]/.test(value)) return "Password must contain at least one special character";
  return null;
}

export function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("user@example.com");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRegister(event: FormEvent) {
    event.preventDefault();
    setError(null);

    const nameError = validateName(firstName, "First name") ?? validateName(lastName, "Last name");
    if (nameError) {
      setError(nameError);
      return;
    }
    if (!EMAIL_PATTERN.test(email.trim())) {
      setError("Enter a valid email address");
      return;
    }
    if (!PHONE_PATTERN.test(phone.trim())) {
      setError("Enter a valid phone number in international format, e.g. +40712345678");
      return;
    }
    const passwordError = validatePassword(password);
    if (passwordError) {
      setError(passwordError);
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match");
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
      });
      navigate("/onboarding");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create account");
    } finally {
      setSubmitting(false);
    }
  }

  if (mode === "register") {
    return (
      <form onSubmit={handleRegister} className="auth-form">
        <div className="auth-form__header">
          <span className="eyebrow">Step 1</span>
          <h2>Create account</h2>
        </div>
        <div className="auth-form__grid">
          <label>
            First name
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
            Last name
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
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </label>
        <label>
          Phone
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
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
          <small className="auth-field-hint">
            At least 8 characters, with an uppercase letter, a lowercase letter, a digit and a special character.
          </small>
        </label>
        <label>
          Confirm password
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            autoComplete="new-password"
          />
        </label>
        {error && (
          <p role="alert" className="status-line status-line--error">
            {error}
          </p>
        )}
        <button type="submit" disabled={submitting}>
          {submitting ? "Creating account..." : "Create account"}
        </button>
        <p className="auth-switch">
          Already have an account?{" "}
          <button type="button" className="button-link" onClick={() => setMode("login")}>
            Sign in
          </button>
        </p>
      </form>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="auth-form">
      <label>
        Email
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      <label>
        Password
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Signing in..." : "Sign in"}
      </button>
      <p className="auth-switch">
        Don't have an account?{" "}
        <button type="button" className="button-link" onClick={() => setMode("register")}>
          Create account
        </button>
      </p>
    </form>
  );
}
