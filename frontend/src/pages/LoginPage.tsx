import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";

type AuthMode = "login" | "register";

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
            <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required autoComplete="given-name" />
          </label>
          <label>
            Last name
            <input value={lastName} onChange={(e) => setLastName(e.target.value)} required autoComplete="family-name" />
          </label>
        </div>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </label>
        <label>
          Phone
          <input value={phone} onChange={(e) => setPhone(e.target.value)} required autoComplete="tel" />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="new-password"
          />
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
