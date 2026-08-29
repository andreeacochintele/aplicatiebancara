import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../api/apiClient";
import {
  getMyFullProfile,
  skipOnboardingStep4,
  submitIdentityDocument,
  updateOnboardingStep2,
  updateOnboardingStep4,
} from "../features/auth";
import { CountrySearchSelect } from "../features/auth/CountrySearchSelect";
import { NationalitySearchSelect } from "../features/auth/NationalitySearchSelect";
import { DropdownWithOther } from "../features/auth/DropdownWithOther";
import { FileField } from "../features/auth/FileField";
import { EMPLOYMENT_STATUSES_WITHOUT_EMPLOYER, INCOME_SOURCE_OPTIONS, INDUSTRY_OPTIONS } from "../features/auth/employmentOptions";
import {
  cnpMatchesDateOfBirth,
  validateAddressToken,
  validateCnp,
  validateDateOfBirth,
  validateMonthlyIncome,
  validateOccupation,
  validateOptionalFreeText,
  validatePostalCode,
  validateStreet,
} from "../features/auth/onboardingValidation";
import { useAuth } from "../hooks/useAuth";
import type { EmploymentStatus, OnboardingStep2Payload, OnboardingStep4Payload, UserFullProfile } from "../types";

const steps = [
  { number: 1, labelKey: "onboarding.stepAccount" },
  { number: 2, labelKey: "onboarding.stepPersonal" },
  { number: 3, labelKey: "onboarding.stepIdentity" },
  { number: 4, labelKey: "onboarding.stepFinancial" },
];

const employmentStatuses: Array<{ value: EmploymentStatus; labelKey: string }> = [
  { value: "EMPLOYED", labelKey: "onboarding.employed" },
  { value: "SELF_EMPLOYED", labelKey: "onboarding.selfEmployed" },
  { value: "STUDENT", labelKey: "onboarding.student" },
  { value: "UNEMPLOYED", labelKey: "onboarding.unemployed" },
  { value: "RETIRED", labelKey: "onboarding.retired" },
  { value: "OTHER", labelKey: "onboarding.other" },
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

const todayIso = new Date().toISOString().slice(0, 10);
const MAX_IDENTITY_DOCUMENT_ATTEMPTS = 3;

export function OnboardingPage() {
  const { t } = useTranslation();
  const { accessToken, logout, markOnboardingCompleted } = useAuth();
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

  const [step3, setStep3] = useState<{ front: string; back: string }>({ front: "", back: "" });

  const [viewStep, setViewStep] = useState<number | null>(null);

  function stepFromProfile(source: UserFullProfile): number {
    const step = source.onboarding.completed ? 4 : (source.onboarding.pending_step ?? 2);
    return Math.max(2, Math.min(4, step));
  }

  const activeStep = viewStep ?? (profile ? stepFromProfile(profile) : 2);

  function goBack() {
    setViewStep((current) => Math.max(2, (current ?? activeStep) - 1));
  }

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
        setViewStep(stepFromProfile(nextProfile));
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          navigate("/login", { replace: true });
          return;
        }
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : t("onboarding.couldNotLoad"));
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

  function validateStep2(): string | null {
    const cnpError = validateCnp(step2.cnp);
    if (cnpError) return cnpError;
    const dobError = validateDateOfBirth(step2.date_of_birth);
    if (dobError) return dobError;
    if (!cnpMatchesDateOfBirth(step2.cnp, step2.date_of_birth)) {
      return t("onboarding.cnpDobMismatch");
    }
    const streetError = validateStreet(step2.street);
    if (streetError) return streetError;
    for (const field of ["building", "staircase", "apartment"] as const) {
      const tokenError = validateAddressToken(step2[field] ?? "");
      if (tokenError) return tokenError;
    }
    const postalCodeError = validatePostalCode(step2.postal_code ?? "");
    if (postalCodeError) return postalCodeError;
    return null;
  }

  async function submitStep2(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    const validationError = validateStep2();
    if (validationError) {
      setError(validationError);
      return;
    }
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
      setViewStep(stepFromProfile(response));
    } catch (err) {
      handleApiError(err, t("onboarding.couldNotSavePersonalDetails"));
    } finally {
      setSubmitting(false);
    }
  }

  async function submitStep3(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    if (!step3.front || !step3.back) {
      setError(t("onboarding.selectBothIdPhotos"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await submitIdentityDocument(accessToken, {
        front_image_base64: step3.front,
        back_image_base64: step3.back,
      });
      setProfile(response);
      setViewStep(stepFromProfile(response));
      setStep3({ front: "", back: "" });
      if (response.identity_document.status !== "VERIFIED" && response.identity_document.failure_reason) {
        setError(response.identity_document.failure_reason);
      }
    } catch (err) {
      handleApiError(err, t("onboarding.couldNotVerifyIdentity"));
    } finally {
      setSubmitting(false);
    }
  }

  function validateStep4(): string | null {
    const occupationError = validateOccupation(step4.occupation ?? "");
    if (occupationError) return occupationError;
    const employerError = validateOptionalFreeText(step4.employer ?? "", t("onboarding.employer"));
    if (employerError) return employerError;
    const industryError = validateOptionalFreeText(step4.industry ?? "", t("onboarding.industry"));
    if (industryError) return industryError;
    const incomeSourceError = validateOptionalFreeText(step4.income_source ?? "", t("onboarding.incomeSource"));
    if (incomeSourceError) return incomeSourceError;
    const incomeError = validateMonthlyIncome(step4.approximate_monthly_income ?? "");
    if (incomeError) return incomeError;
    return null;
  }

  async function submitStep4(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    const validationError = validateStep4();
    if (validationError) {
      setError(validationError);
      return;
    }
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
      markOnboardingCompleted();
      navigate("/dashboard", { replace: true });
    } catch (err) {
      handleApiError(err, t("onboarding.couldNotFinishOnboarding"));
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
      markOnboardingCompleted();
      navigate("/dashboard", { replace: true });
    } catch (err) {
      handleApiError(err, t("onboarding.couldNotSkipFinancialProfile"));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="onboarding-shell">
        <section className="onboarding-card">
          <p>{t("onboarding.loadingOnboarding")}</p>
        </section>
      </div>
    );
  }

  return (
    <div className="onboarding-shell">
      <section className="onboarding-card">
        <div className="onboarding-card__header">
          <div>
            <span className="eyebrow">{t("onboarding.eyebrow")}</span>
            <h1>{t("onboarding.title")}</h1>
          </div>
          <button type="button" className="button--ghost" onClick={logout}>
            {t("onboarding.logout")}
          </button>
        </div>

        <ol className="onboarding-progress" aria-label={t("onboarding.progressLabel")}>
          {progress.map((step) => (
            <li key={step.number} className={`onboarding-progress__step onboarding-progress__step--${step.state}`}>
              <span>{step.number}</span>
              <strong>{t(step.labelKey)}</strong>
            </li>
          ))}
        </ol>

        {activeStep > 2 && (
          <button type="button" className="button--ghost onboarding-back" disabled={submitting} onClick={goBack}>
            {t("onboarding.back")}
          </button>
        )}

        {error && (
          <p role="alert" className="status-line status-line--error">
            {error}
          </p>
        )}

        {activeStep === 2 && (
          <form onSubmit={submitStep2} className="onboarding-form">
            <div className="auth-form__header">
              <span className="eyebrow">{t("onboarding.step2")}</span>
              <h2>{t("onboarding.personalDetails")}</h2>
            </div>
            <div className="onboarding-form__grid">
              <Field
                label={t("onboarding.cnp")}
                value={step2.cnp}
                onChange={(e) => setStep2({ ...step2, cnp: e.target.value })}
                required
                inputMode="numeric"
                maxLength={13}
              />
              <Field
                label={t("onboarding.dateOfBirth")}
                type="date"
                value={step2.date_of_birth}
                onChange={(e) => setStep2({ ...step2, date_of_birth: e.target.value })}
                required
                min="1900-01-01"
                max={todayIso}
              />
              <NationalitySearchSelect
                label={t("onboarding.citizenship")}
                value={step2.citizenship}
                onChange={(demonym) => setStep2({ ...step2, citizenship: demonym })}
                required
                placeholder={t("onboarding.citizenshipPlaceholder")}
              />
              <CountrySearchSelect
                label={t("onboarding.country")}
                value={step2.country}
                onChange={(name) => setStep2({ ...step2, country: name })}
                required
                placeholder={t("onboarding.countryPlaceholder")}
              />
              <Field
                label={t("onboarding.county")}
                value={step2.county}
                onChange={(e) => setStep2({ ...step2, county: e.target.value })}
                required
              />
              <Field label={t("onboarding.city")} value={step2.city} onChange={(e) => setStep2({ ...step2, city: e.target.value })} required />
              <Field
                label={t("onboarding.street")}
                value={step2.street}
                onChange={(e) => setStep2({ ...step2, street: e.target.value })}
                required
              />
              <Field
                label={t("onboarding.streetNumber")}
                value={step2.street_number}
                onChange={(e) => setStep2({ ...step2, street_number: e.target.value })}
                required
              />
              <Field
                label={t("onboarding.building")}
                value={step2.building ?? ""}
                onChange={(e) => setStep2({ ...step2, building: e.target.value })}
                maxLength={32}
              />
              <Field
                label={t("onboarding.staircase")}
                value={step2.staircase ?? ""}
                onChange={(e) => setStep2({ ...step2, staircase: e.target.value })}
                maxLength={32}
              />
              <Field
                label={t("onboarding.apartment")}
                value={step2.apartment ?? ""}
                onChange={(e) => setStep2({ ...step2, apartment: e.target.value })}
                maxLength={32}
              />
              <Field
                label={t("onboarding.postalCode")}
                value={step2.postal_code ?? ""}
                onChange={(e) => setStep2({ ...step2, postal_code: e.target.value })}
                maxLength={12}
              />
            </div>
            <button type="submit" disabled={submitting}>
              {submitting ? t("onboarding.saving") : t("onboarding.continue")}
            </button>
          </form>
        )}

        {activeStep === 3 && (
          <div className="onboarding-placeholder">
            <div className="auth-form__header">
              <span className="eyebrow">{t("onboarding.step3")}</span>
              <h2>{t("onboarding.identityDocument")}</h2>
            </div>
            {profile?.identity_document.status === "NEEDS_REVIEW" ? (
              <p>{t("onboarding.needsReviewNotice", { maxAttempts: MAX_IDENTITY_DOCUMENT_ATTEMPTS })}</p>
            ) : profile?.identity_document.status === "REJECTED" ? (
              <p>{t("onboarding.rejectedNotice")}</p>
            ) : (
              <form onSubmit={submitStep3} className="onboarding-form">
                <p className="field-hint">{t("onboarding.uploadHint")}</p>
                <div className="onboarding-form__grid">
                  <FileField
                    label={t("onboarding.frontOfId")}
                    disabled={submitting}
                    onFileSelected={(dataUrl) => setStep3((current) => ({ ...current, front: dataUrl }))}
                  />
                  <FileField
                    label={t("onboarding.backOfId")}
                    disabled={submitting}
                    onFileSelected={(dataUrl) => setStep3((current) => ({ ...current, back: dataUrl }))}
                  />
                </div>
                {profile && profile.identity_document.attempt_count > 0 && (
                  <p className="field-hint">
                    {t("onboarding.attemptCount", { current: profile.identity_document.attempt_count, max: MAX_IDENTITY_DOCUMENT_ATTEMPTS })}
                  </p>
                )}
                <button type="submit" disabled={submitting || !step3.front || !step3.back}>
                  {submitting ? t("onboarding.verifying") : t("onboarding.uploadAndVerify")}
                </button>
              </form>
            )}
          </div>
        )}

        {activeStep === 4 && (
          <form onSubmit={submitStep4} className="onboarding-form">
            <div className="auth-form__header">
              <span className="eyebrow">{t("onboarding.step4")}</span>
              <h2>{t("onboarding.financialProfile")}</h2>
            </div>
            <div className="onboarding-form__grid">
              <Field
                label={t("onboarding.occupation")}
                value={step4.occupation ?? ""}
                onChange={(e) => setStep4({ ...step4, occupation: e.target.value })}
                maxLength={100}
              />
              <SelectField
                label={t("onboarding.employmentStatus")}
                value={step4.employment_status ?? ""}
                onChange={(e) => {
                  const nextStatus = e.target.value === "" ? null : (e.target.value as EmploymentStatus);
                  const hidesEmployer = nextStatus !== null && EMPLOYMENT_STATUSES_WITHOUT_EMPLOYER.has(nextStatus);
                  setStep4({
                    ...step4,
                    employment_status: nextStatus,
                    employer: hidesEmployer ? "" : step4.employer,
                    industry: hidesEmployer ? "" : step4.industry,
                  });
                }}
              >
                <option value="">{t("onboarding.selectStatus")}</option>
                {employmentStatuses.map((status) => (
                  <option key={status.value} value={status.value}>
                    {t(status.labelKey)}
                  </option>
                ))}
              </SelectField>
              {!(step4.employment_status && EMPLOYMENT_STATUSES_WITHOUT_EMPLOYER.has(step4.employment_status)) && (
                <>
                  <Field
                    label={t("onboarding.employer")}
                    value={step4.employer ?? ""}
                    onChange={(e) => setStep4({ ...step4, employer: e.target.value })}
                    maxLength={255}
                  />
                  <DropdownWithOther
                    label={t("onboarding.industry")}
                    value={step4.industry ?? ""}
                    options={INDUSTRY_OPTIONS}
                    onChange={(value) => setStep4({ ...step4, industry: value })}
                  />
                </>
              )}
              <DropdownWithOther
                label={t("onboarding.incomeSource")}
                value={step4.income_source ?? ""}
                options={INCOME_SOURCE_OPTIONS}
                onChange={(value) => setStep4({ ...step4, income_source: value })}
              />
              <Field
                label={t("onboarding.approximateMonthlyIncome")}
                type="number"
                min="0"
                max="10000000"
                step="0.01"
                value={step4.approximate_monthly_income ?? ""}
                onChange={(e) => setStep4({ ...step4, approximate_monthly_income: e.target.value })}
              />
            </div>
            <label>
              {t("onboarding.accountPurpose")}
              <input
                value={step4.account_purpose ?? ""}
                onChange={(e) => setStep4({ ...step4, account_purpose: e.target.value })}
              />
            </label>
            <div className="form-actions">
              <button type="submit" disabled={submitting}>
                {submitting ? t("onboarding.finishing") : t("onboarding.finish")}
              </button>
              <button type="button" className="button--ghost" disabled={submitting} onClick={skipStep4}>
                {t("onboarding.skipForNow")}
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
