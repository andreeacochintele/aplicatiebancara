import {
  useEffect,
  useState,
  type FormEvent,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

import { ApiError } from "../api/apiClient";
import { getMyFullProfile, updateMyProfile } from "../features/auth";
import { CountrySearchSelect } from "../features/auth/CountrySearchSelect";
import { DropdownWithOther } from "../features/auth/DropdownWithOther";
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

const NAME_PATTERN = /^\p{L}+(?:[ '-]\p{L}+)*$/u;
const PHONE_PATTERN = /^\+[1-9]\d{7,14}$/;
const todayIso = new Date().toISOString().slice(0, 10);

function validateName(value: string, label: string): string | null {
  const trimmed = value.trim();
  if (trimmed.length < 2 || trimmed.length > 50) return `${label} must be between 2 and 50 characters`;
  if (!NAME_PATTERN.test(trimmed)) return `${label} must contain only letters`;
  return null;
}

function validatePhone(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!PHONE_PATTERN.test(trimmed)) return "Enter a valid phone number in international format, e.g. +40712345678";
  return null;
}

function cleanOptional(value: string) {
  return value.trim() === "" ? null : value.trim();
}

function Field({ label, ...props }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
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

export function ProfilePage() {
  const { accessToken } = useAuth();
  const [profile, setProfile] = useState<UserFullProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [account, setAccount] = useState({ first_name: "", last_name: "", phone: "" });
  const [accountError, setAccountError] = useState<string | null>(null);
  const [accountSaved, setAccountSaved] = useState(false);
  const [accountSaving, setAccountSaving] = useState(false);

  const [personal, setPersonal] = useState<OnboardingStep2Payload>({
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
  const [personalError, setPersonalError] = useState<string | null>(null);
  const [personalSaved, setPersonalSaved] = useState(false);
  const [personalSaving, setPersonalSaving] = useState(false);

  const [employment, setEmployment] = useState<OnboardingStep4Payload>({
    occupation: "",
    employer: "",
    industry: "",
    employment_status: null,
    income_source: "",
    approximate_monthly_income: "",
    account_purpose: "",
  });
  const [employmentError, setEmploymentError] = useState<string | null>(null);
  const [employmentSaved, setEmploymentSaved] = useState(false);
  const [employmentSaving, setEmploymentSaving] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    getMyFullProfile(accessToken)
      .then((data) => {
        if (cancelled) return;
        setProfile(data);
        setAccount({ first_name: data.user.first_name, last_name: data.user.last_name, phone: data.user.phone ?? "" });
        setPersonal({
          cnp: data.profile.cnp ?? "",
          date_of_birth: data.profile.date_of_birth ?? "",
          citizenship: data.profile.citizenship ?? "",
          country: data.address.country ?? "",
          county: data.address.county ?? "",
          city: data.address.city ?? "",
          street: data.address.street ?? "",
          street_number: data.address.street_number ?? "",
          building: data.address.building ?? "",
          staircase: data.address.staircase ?? "",
          apartment: data.address.apartment ?? "",
          postal_code: data.address.postal_code ?? "",
        });
        setEmployment({
          occupation: data.employment.occupation ?? "",
          employer: data.employment.employer ?? "",
          industry: data.employment.industry ?? "",
          employment_status: data.employment.employment_status,
          income_source: data.employment.income_source ?? "",
          approximate_monthly_income: data.employment.approximate_monthly_income ?? "",
          account_purpose: data.employment.account_purpose ?? "",
        });
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Could not load profile"))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  // CNP is a verified government ID once set; only legacy accounts without one yet can fill it in here.
  const cnpIsLocked = profile !== null && !!profile.profile.cnp;

  async function submitAccount(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    const nameError = validateName(account.first_name, "First name") ?? validateName(account.last_name, "Last name");
    if (nameError) {
      setAccountError(nameError);
      return;
    }
    const phoneError = validatePhone(account.phone);
    if (phoneError) {
      setAccountError(phoneError);
      return;
    }

    setAccountSaving(true);
    setAccountError(null);
    setAccountSaved(false);
    try {
      const response = await updateMyProfile(accessToken, {
        first_name: account.first_name.trim(),
        last_name: account.last_name.trim(),
        phone: account.phone.trim(),
      });
      setProfile(response);
      setAccountSaved(true);
    } catch (err) {
      setAccountError(err instanceof ApiError ? err.message : "Could not save account details");
    } finally {
      setAccountSaving(false);
    }
  }

  function validatePersonal(): string | null {
    if (!cnpIsLocked) {
      const cnpError = validateCnp(personal.cnp);
      if (cnpError) return cnpError;
      const dobError = validateDateOfBirth(personal.date_of_birth);
      if (dobError) return dobError;
      if (!cnpMatchesDateOfBirth(personal.cnp, personal.date_of_birth)) {
        return "CNP does not match the date of birth provided";
      }
    }
    const streetError = validateStreet(personal.street);
    if (streetError) return streetError;
    for (const field of ["building", "staircase", "apartment"] as const) {
      const tokenError = validateAddressToken(personal[field] ?? "");
      if (tokenError) return tokenError;
    }
    const postalCodeError = validatePostalCode(personal.postal_code ?? "");
    if (postalCodeError) return postalCodeError;
    return null;
  }

  async function submitPersonal(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    const validationError = validatePersonal();
    if (validationError) {
      setPersonalError(validationError);
      return;
    }

    setPersonalSaving(true);
    setPersonalError(null);
    setPersonalSaved(false);
    try {
      const response = await updateMyProfile(accessToken, {
        step_2: {
          ...personal,
          building: cleanOptional(personal.building ?? ""),
          staircase: cleanOptional(personal.staircase ?? ""),
          apartment: cleanOptional(personal.apartment ?? ""),
          postal_code: cleanOptional(personal.postal_code ?? ""),
        },
      });
      setProfile(response);
      setPersonalSaved(true);
    } catch (err) {
      setPersonalError(err instanceof ApiError ? err.message : "Could not save personal details");
    } finally {
      setPersonalSaving(false);
    }
  }

  function validateEmploymentForm(): string | null {
    const occupationError = validateOccupation(employment.occupation ?? "");
    if (occupationError) return occupationError;
    const employerError = validateOptionalFreeText(employment.employer ?? "", "Employer");
    if (employerError) return employerError;
    const industryError = validateOptionalFreeText(employment.industry ?? "", "Industry");
    if (industryError) return industryError;
    const incomeSourceError = validateOptionalFreeText(employment.income_source ?? "", "Income source");
    if (incomeSourceError) return incomeSourceError;
    const incomeError = validateMonthlyIncome(employment.approximate_monthly_income ?? "");
    if (incomeError) return incomeError;
    return null;
  }

  async function submitEmployment(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    const validationError = validateEmploymentForm();
    if (validationError) {
      setEmploymentError(validationError);
      return;
    }

    setEmploymentSaving(true);
    setEmploymentError(null);
    setEmploymentSaved(false);
    try {
      const response = await updateMyProfile(accessToken, {
        employment: {
          occupation: cleanOptional(employment.occupation ?? ""),
          employer: cleanOptional(employment.employer ?? ""),
          industry: cleanOptional(employment.industry ?? ""),
          employment_status: employment.employment_status,
          income_source: cleanOptional(employment.income_source ?? ""),
          approximate_monthly_income: cleanOptional(employment.approximate_monthly_income ?? ""),
          account_purpose: cleanOptional(employment.account_purpose ?? ""),
        },
      });
      setProfile(response);
      setEmploymentSaved(true);
    } catch (err) {
      setEmploymentError(err instanceof ApiError ? err.message : "Could not save financial profile");
    } finally {
      setEmploymentSaving(false);
    }
  }

  if (loading) {
    return (
      <section className="tile">
        <p>Loading profile...</p>
      </section>
    );
  }

  if (loadError || !profile) {
    return (
      <section className="tile">
        <p role="alert" className="status-line status-line--error">
          {loadError ?? "Could not load profile"}
        </p>
      </section>
    );
  }

  const hidesEmployer = Boolean(
    employment.employment_status && EMPLOYMENT_STATUSES_WITHOUT_EMPLOYER.has(employment.employment_status),
  );

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <form onSubmit={submitAccount} className="tile onboarding-form">
        <div className="auth-form__header">
          <span className="eyebrow">Account</span>
          <h2>Basic details</h2>
        </div>
        <div className="onboarding-form__grid">
          <Field
            label="First name"
            value={account.first_name}
            onChange={(e) => setAccount({ ...account, first_name: e.target.value })}
            required
            minLength={2}
            maxLength={50}
          />
          <Field
            label="Last name"
            value={account.last_name}
            onChange={(e) => setAccount({ ...account, last_name: e.target.value })}
            required
            minLength={2}
            maxLength={50}
          />
          <Field label="Email" value={profile.user.email} disabled />
          <Field
            label="Phone"
            value={account.phone}
            onChange={(e) => setAccount({ ...account, phone: e.target.value })}
            placeholder="+40712345678"
          />
        </div>
        {accountError && (
          <p role="alert" className="status-line status-line--error">
            {accountError}
          </p>
        )}
        {accountSaved && <p className="status-line">Saved.</p>}
        <button type="submit" disabled={accountSaving}>
          {accountSaving ? "Saving..." : "Save"}
        </button>
      </form>

      <form onSubmit={submitPersonal} className="tile onboarding-form">
        <div className="auth-form__header">
          <span className="eyebrow">Personal</span>
          <h2>Identity &amp; address</h2>
        </div>
        <div className="onboarding-form__grid">
          <Field
            label="CNP"
            value={personal.cnp}
            onChange={(e) => setPersonal({ ...personal, cnp: e.target.value })}
            required
            disabled={cnpIsLocked}
            inputMode="numeric"
            maxLength={13}
          />
          <Field
            label="Date of birth"
            type="date"
            value={personal.date_of_birth}
            onChange={(e) => setPersonal({ ...personal, date_of_birth: e.target.value })}
            required
            disabled={cnpIsLocked}
            min="1900-01-01"
            max={todayIso}
          />
          <CountrySearchSelect
            label="Citizenship"
            value={personal.citizenship}
            onChange={(name) => setPersonal({ ...personal, citizenship: name })}
            required
            placeholder="Start typing a country..."
          />
          <CountrySearchSelect
            label="Country"
            value={personal.country}
            onChange={(name) => setPersonal({ ...personal, country: name })}
            required
            placeholder="Start typing a country..."
          />
          <Field
            label="County"
            value={personal.county}
            onChange={(e) => setPersonal({ ...personal, county: e.target.value })}
            required
          />
          <Field label="City" value={personal.city} onChange={(e) => setPersonal({ ...personal, city: e.target.value })} required />
          <Field
            label="Street"
            value={personal.street}
            onChange={(e) => setPersonal({ ...personal, street: e.target.value })}
            required
          />
          <Field
            label="Street number"
            value={personal.street_number}
            onChange={(e) => setPersonal({ ...personal, street_number: e.target.value })}
            required
          />
          <Field
            label="Building"
            value={personal.building ?? ""}
            onChange={(e) => setPersonal({ ...personal, building: e.target.value })}
            maxLength={32}
          />
          <Field
            label="Staircase"
            value={personal.staircase ?? ""}
            onChange={(e) => setPersonal({ ...personal, staircase: e.target.value })}
            maxLength={32}
          />
          <Field
            label="Apartment"
            value={personal.apartment ?? ""}
            onChange={(e) => setPersonal({ ...personal, apartment: e.target.value })}
            maxLength={32}
          />
          <Field
            label="Postal code"
            value={personal.postal_code ?? ""}
            onChange={(e) => setPersonal({ ...personal, postal_code: e.target.value })}
            maxLength={12}
          />
        </div>
        {personalError && (
          <p role="alert" className="status-line status-line--error">
            {personalError}
          </p>
        )}
        {personalSaved && <p className="status-line">Saved.</p>}
        <button type="submit" disabled={personalSaving}>
          {personalSaving ? "Saving..." : "Save"}
        </button>
      </form>

      <form onSubmit={submitEmployment} className="tile onboarding-form">
        <div className="auth-form__header">
          <span className="eyebrow">Financial</span>
          <h2>Employment &amp; income</h2>
        </div>
        <div className="onboarding-form__grid">
          <Field
            label="Occupation"
            value={employment.occupation ?? ""}
            onChange={(e) => setEmployment({ ...employment, occupation: e.target.value })}
            maxLength={100}
          />
          <SelectField
            label="Employment status"
            value={employment.employment_status ?? ""}
            onChange={(e) => {
              const nextStatus = e.target.value === "" ? null : (e.target.value as EmploymentStatus);
              const hides = nextStatus !== null && EMPLOYMENT_STATUSES_WITHOUT_EMPLOYER.has(nextStatus);
              setEmployment({
                ...employment,
                employment_status: nextStatus,
                employer: hides ? "" : employment.employer,
                industry: hides ? "" : employment.industry,
              });
            }}
          >
            <option value="">Select status</option>
            <option value="EMPLOYED">Employed</option>
            <option value="SELF_EMPLOYED">Self-employed</option>
            <option value="STUDENT">Student</option>
            <option value="UNEMPLOYED">Unemployed</option>
            <option value="RETIRED">Retired</option>
            <option value="OTHER">Other</option>
          </SelectField>
          {!hidesEmployer && (
            <>
              <Field
                label="Employer"
                value={employment.employer ?? ""}
                onChange={(e) => setEmployment({ ...employment, employer: e.target.value })}
                maxLength={255}
              />
              <DropdownWithOther
                label="Industry"
                value={employment.industry ?? ""}
                options={INDUSTRY_OPTIONS}
                onChange={(value) => setEmployment({ ...employment, industry: value })}
              />
            </>
          )}
          <DropdownWithOther
            label="Income source"
            value={employment.income_source ?? ""}
            options={INCOME_SOURCE_OPTIONS}
            onChange={(value) => setEmployment({ ...employment, income_source: value })}
          />
          <Field
            label="Approximate monthly income"
            type="number"
            min="0"
            max="10000000"
            step="0.01"
            value={employment.approximate_monthly_income ?? ""}
            onChange={(e) => setEmployment({ ...employment, approximate_monthly_income: e.target.value })}
          />
        </div>
        <label>
          Account purpose
          <input
            value={employment.account_purpose ?? ""}
            onChange={(e) => setEmployment({ ...employment, account_purpose: e.target.value })}
          />
        </label>
        {employmentError && (
          <p role="alert" className="status-line status-line--error">
            {employmentError}
          </p>
        )}
        {employmentSaved && <p className="status-line">Saved.</p>}
        <button type="submit" disabled={employmentSaving}>
          {employmentSaving ? "Saving..." : "Save"}
        </button>
      </form>
    </section>
  );
}
