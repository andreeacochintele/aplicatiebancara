import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../api/apiClient";
import {
  createIdentityDocumentPlaceholder,
  getMyFullProfile,
  skipOnboardingStep4,
  updateOnboardingStep2,
  updateOnboardingStep4,
} from "../features/auth";
import { useAuth } from "../hooks/useAuth";
import type { EmploymentStatus, OnboardingStep2Payload, OnboardingStep4Payload, UserFullProfile } from "../types";

const steps = [
  { number: 1, label: "Account" },
  { number: 2, label: "Personal" },
  { number: 3, label: "Identity" },
  { number: 4, label: "Financial" },
];

const employmentStatuses: Array<{ value: EmploymentStatus; label: string }> = [
  { value: "EMPLOYED", label: "Employed" },
  { value: "SELF_EMPLOYED", label: "Self-employed" },
  { value: "STUDENT", label: "Student" },
  { value: "UNEMPLOYED", label: "Unemployed" },
  { value: "RETIRED", label: "Retired" },
  { value: "OTHER", label: "Other" },
];

function cleanOptional(value: string) {
  return value.trim() === "" ? null : value.trim();
}

function Field({
  label,
  ...props
}: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label>
      {label}
      <input {...props} />
    </label>
  );
}

function SelectField({
  label,
  children,
  ...props
}: { label: string; children: ReactNode } & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <label>
      {label}
      <select {...props}>{children}</select>
    </label>
  );
}

export function OnboardingPage() {
  const { accessToken, logout } = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<UserFullProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [step2, setStep2] = useState<OnboardingStep2Payload>({
    cnp: "",
    date_of_birth: "",
    citizenship: "",
    country: "",
    county: "",
    city: "",
    street: "",
    street_number: "",
    building: "",
    staircase: "",
    apartment: "",
    postal_code: "",
  });
  const [step4, setStep4] = useState<OnboardingStep4Payload>({
    occupation: "",
    employer: "",
    industry: "",
    employment_status: null,
    income_source: "",
    approximate_monthly_income: "",
    account_purpose: "",
  });

  const currentStep = profile?.onboarding.completed ? 4 : (profile?.onboarding.pending_step ?? 2);
  const activeStep = Math.max(2, Math.min(4, currentStep));

  useEffect(() => {
    let cancelled = false;
    async function loadProfile() {
      if (!accessToken) return;
      setLoading(true);
      setError(null);
      try {
        const nextProfile = await getMyFullProfile(accessToken);
        if (cancelled) return;
        if (nextProfile.onboarding.completed) {
          navigate("/dashboard", { replace: true });
          return;
        }
        setProfile(nextProfile);
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          navigate("/login", { replace: true });
          return;
        }
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load onboarding");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    loadProfile();
    return () => {
      cancelled = true;
    };
  }, [accessToken, logout, navigate]);

  useEffect(() => {
    if (!profile) return;
    setStep2({
      cnp: profile.profile.cnp ?? "",
      date_of_birth: profile.profile.date_of_birth ?? "",
      citizenship: profile.profile.citizenship ?? "",
      country: profile.address.country ?? "",
      county: profile.address.county ?? "",
      city: profile.address.city ?? "",
      street: profile.address.street ?? "",
      street_number: profile.address.street_number ?? "",
      building: profile.address.building ?? "",
      staircase: profile.address.staircase ?? "",
      apartment: profile.address.apartment ?? "",
      postal_code: profile.address.postal_code ?? "",
    });
    setStep4({
      occupation: profile.employment.occupation ?? "",
      employer: profile.employment.employer ?? "",
      industry: profile.employment.industry ?? "",
      employment_status: profile.employment.employment_status,
      income_source: profile.employment.income_source ?? "",
      approximate_monthly_income: profile.employment.approximate_monthly_income ?? "",
      account_purpose: profile.employment.account_purpose ?? "",
    });
  }, [profile]);

  const progress = useMemo(
    () =>
      steps.map((step) => ({
        ...step,
        state: step.number < activeStep ? "complete" : step.number === activeStep ? "active" : "pending",
      })),
    [activeStep],
  );

  function handleApiError(err: unknown, fallback: string) {
    setError(err instanceof ApiError ? err.message : fallback);
  }

  async function submitStep2(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await updateOnboardingStep2(accessToken, {
        ...step2,
        building: cleanOptional(step2.building ?? ""),
        staircase: cleanOptional(step2.staircase ?? ""),
        apartment: cleanOptional(step2.apartment ?? ""),
        postal_code: cleanOptional(step2.postal_code ?? ""),
      });
      setProfile(response);
    } catch (err) {
      handleApiError(err, "Could not save personal details");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitStep3() {
    if (!accessToken) return;
    setSubmitting(true);
    setError(null);
    try {
      setProfile(await createIdentityDocumentPlaceholder(accessToken));
    } catch (err) {
      handleApiError(err, "Could not continue identity step");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitStep4(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await updateOnboardingStep4(accessToken, {
        occupation: cleanOptional(step4.occupation ?? ""),
        employer: cleanOptional(step4.employer ?? ""),
        industry: cleanOptional(step4.industry ?? ""),
        employment_status: step4.employment_status,
        income_source: cleanOptional(step4.income_source ?? ""),
        approximate_monthly_income: cleanOptional(step4.approximate_monthly_income ?? ""),
        account_purpose: cleanOptional(step4.account_purpose ?? ""),
      });
      setProfile(response);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      handleApiError(err, "Could not finish onboarding");
    } finally {
      setSubmitting(false);
    }
  }

  async function skipStep4() {
    if (!accessToken) return;
    setSubmitting(true);
    setError(null);
    try {
      await skipOnboardingStep4(accessToken);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      handleApiError(err, "Could not skip financial profile");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="onboarding-shell">
        <section className="onboarding-card">
          <p>Loading onboarding...</p>
        </section>
      </div>
    );
  }

  return (
    <div className="onboarding-shell">
      <section className="onboarding-card">
        <div className="onboarding-card__header">
          <div>
            <span className="eyebrow">Aurora onboarding</span>
            <h1>Finish setting up your account</h1>
          </div>
          <button type="button" className="button--ghost" onClick={logout}>
            Logout
          </button>
        </div>

        <ol className="onboarding-progress" aria-label="Onboarding progress">
          {progress.map((step) => (
            <li key={step.number} className={`onboarding-progress__step onboarding-progress__step--${step.state}`}>
              <span>{step.number}</span>
              <strong>{step.label}</strong>
            </li>
          ))}
        </ol>

        {error && (
          <p role="alert" className="status-line status-line--error">
            {error}
          </p>
        )}

        {activeStep === 2 && (
          <form onSubmit={submitStep2} className="onboarding-form">
            <div className="auth-form__header">
              <span className="eyebrow">Step 2</span>
              <h2>Personal details</h2>
            </div>
            <div className="onboarding-form__grid">
              <Field label="CNP" value={step2.cnp} onChange={(e) => setStep2({ ...step2, cnp: e.target.value })} required />
              <Field
                label="Date of birth"
                type="date"
                value={step2.date_of_birth}
                onChange={(e) => setStep2({ ...step2, date_of_birth: e.target.value })}
                required
              />
              <Field
                label="Citizenship"
                value={step2.citizenship}
                onChange={(e) => setStep2({ ...step2, citizenship: e.target.value })}
                required
              />
              <Field
                label="Country"
                value={step2.country}
                onChange={(e) => setStep2({ ...step2, country: e.target.value })}
                required
              />
              <Field
                label="County"
                value={step2.county}
                onChange={(e) => setStep2({ ...step2, county: e.target.value })}
                required
              />
              <Field label="City" value={step2.city} onChange={(e) => setStep2({ ...step2, city: e.target.value })} required />
              <Field
                label="Street"
                value={step2.street}
                onChange={(e) => setStep2({ ...step2, street: e.target.value })}
                required
              />
              <Field
                label="Street number"
                value={step2.street_number}
                onChange={(e) => setStep2({ ...step2, street_number: e.target.value })}
                required
              />
              <Field
                label="Building"
                value={step2.building ?? ""}
                onChange={(e) => setStep2({ ...step2, building: e.target.value })}
              />
              <Field
                label="Staircase"
                value={step2.staircase ?? ""}
                onChange={(e) => setStep2({ ...step2, staircase: e.target.value })}
              />
              <Field
                label="Apartment"
                value={step2.apartment ?? ""}
                onChange={(e) => setStep2({ ...step2, apartment: e.target.value })}
              />
              <Field
                label="Postal code"
                value={step2.postal_code ?? ""}
                onChange={(e) => setStep2({ ...step2, postal_code: e.target.value })}
              />
            </div>
            <button type="submit" disabled={submitting}>
              {submitting ? "Saving..." : "Continue"}
            </button>
          </form>
        )}

        {activeStep === 3 && (
          <div className="onboarding-placeholder">
            <div className="auth-form__header">
              <span className="eyebrow">Step 3</span>
              <h2>Identity document</h2>
            </div>
            <p>De făcut când introducem buletine</p>
            <button type="button" disabled={submitting} onClick={submitStep3}>
              {submitting ? "Saving..." : "Continue"}
            </button>
          </div>
        )}

        {activeStep === 4 && (
          <form onSubmit={submitStep4} className="onboarding-form">
            <div className="auth-form__header">
              <span className="eyebrow">Step 4</span>
              <h2>Financial profile</h2>
            </div>
            <div className="onboarding-form__grid">
              <Field
                label="Occupation"
                value={step4.occupation ?? ""}
                onChange={(e) => setStep4({ ...step4, occupation: e.target.value })}
              />
              <Field
                label="Employer"
                value={step4.employer ?? ""}
                onChange={(e) => setStep4({ ...step4, employer: e.target.value })}
              />
              <Field
                label="Industry"
                value={step4.industry ?? ""}
                onChange={(e) => setStep4({ ...step4, industry: e.target.value })}
              />
              <SelectField
                label="Employment status"
                value={step4.employment_status ?? ""}
                onChange={(e) =>
                  setStep4({
                    ...step4,
                    employment_status: e.target.value === "" ? null : (e.target.value as EmploymentStatus),
                  })
                }
              >
                <option value="">Select status</option>
                {employmentStatuses.map((status) => (
                  <option key={status.value} value={status.value}>
                    {status.label}
                  </option>
                ))}
              </SelectField>
              <Field
                label="Income source"
                value={step4.income_source ?? ""}
                onChange={(e) => setStep4({ ...step4, income_source: e.target.value })}
              />
              <Field
                label="Approximate monthly income"
                type="number"
                min="0"
                step="0.01"
                value={step4.approximate_monthly_income ?? ""}
                onChange={(e) => setStep4({ ...step4, approximate_monthly_income: e.target.value })}
              />
            </div>
            <label>
              Account purpose
              <input
                value={step4.account_purpose ?? ""}
                onChange={(e) => setStep4({ ...step4, account_purpose: e.target.value })}
              />
            </label>
            <div className="form-actions">
              <button type="submit" disabled={submitting}>
                {submitting ? "Finishing..." : "Finish"}
              </button>
              <button type="button" className="button--ghost" disabled={submitting} onClick={skipStep4}>
                Skip for now
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
