import { ChevronDown, ChevronUp } from "lucide-react";
import {
  useEffect,
  useState,
  type FormEvent,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

import { ApiError } from "../api/apiClient";
import { getMyFullProfile, submitIdentityDocument, updateMyProfile } from "../features/auth";
import { CountrySearchSelect } from "../features/auth/CountrySearchSelect";
import { DropdownWithOther } from "../features/auth/DropdownWithOther";
import { EMPLOYMENT_STATUSES_WITHOUT_EMPLOYER, INCOME_SOURCE_OPTIONS, INDUSTRY_OPTIONS } from "../features/auth/employmentOptions";
import { FileField } from "../features/auth/FileField";
import { NationalitySearchSelect } from "../features/auth/NationalitySearchSelect";
import {
  validateAddressToken,
  validateMonthlyIncome,
  validateOccupation,
  validateOptionalFreeText,
  validatePostalCode,
  validateStreet,
} from "../features/auth/onboardingValidation";
import { useAuth } from "../hooks/useAuth";
import type { EmploymentStatus, OnboardingStep2Payload, OnboardingStep4Payload, UserFullProfile } from "../types";

const PHONE_PATTERN = /^\+[1-9]\d{7,14}$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function initials(firstName?: string, lastName?: string): string {
  return `${firstName?.[0] ?? ""}${lastName?.[0] ?? ""}`.toUpperCase();
}

function validatePhone(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!PHONE_PATTERN.test(trimmed)) return "Enter a valid phone number in international format, e.g. +40712345678";
  return null;
}

function validateEmail(value: string): string | null {
  if (!EMAIL_PATTERN.test(value.trim())) return "Enter a valid email address";
  return null;
}

function cleanOptional(value: string) {
  return value.trim() === "" ? null : value.trim();
}

function Field({
  label,
  hint,
  ...props
}: { label: string; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label>
      {label}
      <input {...props} />
      {hint && <small className="auth-field-hint">{hint}</small>}
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

function SectionToggle({ label, open, onClick }: { label: string; open: boolean; onClick: () => void }) {
  return (
    <button type="button" className="profile-section__toggle" onClick={onClick} aria-expanded={open}>
      <span>{label}</span>
      {open ? <ChevronUp size={18} strokeWidth={2.2} /> : <ChevronDown size={18} strokeWidth={2.2} />}
    </button>
  );
}

export function ProfilePage() {
  const { accessToken } = useAuth();
  const [profile, setProfile] = useState<UserFullProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [editingContact, setEditingContact] = useState(false);
  const [emailDraft, setEmailDraft] = useState("");
  const [phoneDraft, setPhoneDraft] = useState("");
  const [contactError, setContactError] = useState<string | null>(null);
  const [contactSaving, setContactSaving] = useState(false);

  const [personalOpen, setPersonalOpen] = useState(false);
  const [financialOpen, setFinancialOpen] = useState(false);
  const [identityOpen, setIdentityOpen] = useState(false);

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

  const [identityFiles, setIdentityFiles] = useState<{ front: string; back: string }>({ front: "", back: "" });
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [identitySaved, setIdentitySaved] = useState(false);
  const [identitySaving, setIdentitySaving] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    getMyFullProfile(accessToken)
      .then((data) => {
        if (cancelled) return;
        setProfile(data);
        setEmailDraft(data.user.email);
        setPhoneDraft(data.user.phone ?? "");
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

  function cancelContactEdit() {
    setEmailDraft(profile?.user.email ?? "");
    setPhoneDraft(profile?.user.phone ?? "");
    setContactError(null);
    setEditingContact(false);
  }

  async function submitContact(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    const validationError = validateEmail(emailDraft) ?? validatePhone(phoneDraft);
    if (validationError) {
      setContactError(validationError);
      return;
    }

    setContactSaving(true);
    setContactError(null);
    try {
      const response = await updateMyProfile(accessToken, { email: emailDraft.trim(), phone: phoneDraft.trim() });
      setProfile(response);
      setEditingContact(false);
    } catch (err) {
      setContactError(err instanceof ApiError ? err.message : "Could not save contact details");
    } finally {
      setContactSaving(false);
    }
  }

  // CNP and date of birth are verified identity fields set during onboarding
  // and can't be self-edited here, same as a real KYC record.
  function validatePersonal(): string | null {
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

  async function submitIdentityUpdate(event: FormEvent) {
    event.preventDefault();
    if (!accessToken) return;
    if (!identityFiles.front || !identityFiles.back) {
      setIdentityError("Please select photos of both sides of your ID card");
      return;
    }

    setIdentitySaving(true);
    setIdentityError(null);
    setIdentitySaved(false);
    try {
      const response = await submitIdentityDocument(accessToken, {
        front_image_base64: identityFiles.front,
        back_image_base64: identityFiles.back,
      });
      setProfile(response);
      setIdentitySaved(true);
      setIdentityFiles({ front: "", back: "" });
    } catch (err) {
      setIdentityError(err instanceof ApiError ? err.message : "Could not verify the new identity document");
    } finally {
      setIdentitySaving(false);
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
      <div className="tile profile-header">
        <div className="avatar avatar--large">{initials(profile.user.first_name, profile.user.last_name)}</div>
        <div className="profile-header__info">
          <h1 className="profile-header__name">
            {profile.user.first_name} {profile.user.last_name}
          </h1>
          {editingContact ? (
            <form onSubmit={submitContact} className="profile-header__contact-edit">
              <input
                type="email"
                value={emailDraft}
                onChange={(e) => setEmailDraft(e.target.value)}
                placeholder="you@example.com"
                autoFocus
              />
              <input value={phoneDraft} onChange={(e) => setPhoneDraft(e.target.value)} placeholder="+40712345678" />
              <button type="submit" disabled={contactSaving}>
                {contactSaving ? "Saving..." : "Save"}
              </button>
              <button type="button" className="button--ghost" onClick={cancelContactEdit}>
                Cancel
              </button>
            </form>
          ) : (
            <>
              <div className="profile-header__contact">
                <span>{profile.user.email}</span>
              </div>
              <div className="profile-header__contact">
                <span>{profile.user.phone ?? "No phone on file"}</span>
                <button type="button" className="button-link" onClick={() => setEditingContact(true)}>
                  Edit
                </button>
              </div>
            </>
          )}
          {contactError && (
            <p role="alert" className="status-line status-line--error">
              {contactError}
            </p>
          )}
        </div>
      </div>

      <div className="tile profile-section">
        <SectionToggle label="Personal & address" open={personalOpen} onClick={() => setPersonalOpen((o) => !o)} />
        {personalOpen && (
          <form onSubmit={submitPersonal} className="onboarding-form profile-section__body">
            <div className="onboarding-form__grid">
              <Field
                label="CNP"
                value={personal.cnp}
                disabled
                inputMode="numeric"
                maxLength={13}
                hint="This can't be changed here."
              />
              <Field
                label="Date of birth"
                type="date"
                value={personal.date_of_birth}
                disabled
                hint="This can't be changed here."
              />
              <NationalitySearchSelect
                label="Citizenship"
                value={personal.citizenship}
                onChange={(demonym) => setPersonal({ ...personal, citizenship: demonym })}
                required
                placeholder="Start typing a nationality..."
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
              <Field
                label="City"
                value={personal.city}
                onChange={(e) => setPersonal({ ...personal, city: e.target.value })}
                required
              />
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
        )}
      </div>

      <div className="tile profile-section">
        <SectionToggle label="Financial profile" open={financialOpen} onClick={() => setFinancialOpen((o) => !o)} />
        {financialOpen && (
          <form onSubmit={submitEmployment} className="onboarding-form profile-section__body">
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
        )}
      </div>

      <div className="tile profile-section">
        <SectionToggle label="Identity document" open={identityOpen} onClick={() => setIdentityOpen((o) => !o)} />
        {identityOpen && (
          <div className="profile-section__body">
            {profile?.identity_document.status === "NEEDS_REVIEW" ? (
              <p className="status-line">Your identity document is with an admin for manual review.</p>
            ) : profile?.identity_document.status === "REJECTED" ? (
              <p className="status-line">Your identity document was rejected on review. Please contact support.</p>
            ) : (
              <form onSubmit={submitIdentityUpdate} className="onboarding-form">
                <p className="field-hint">
                  {profile?.identity_document.status === "VERIFIED"
                    ? "Your identity document is verified. Upload new photos here if it was renewed or replaced."
                    : "Upload clear photos of both sides of your Romanian ID card to verify your identity."}
                </p>
                <div className="onboarding-form__grid">
                  <FileField
                    label="Front of ID card"
                    disabled={identitySaving}
                    onFileSelected={(dataUrl) => setIdentityFiles((current) => ({ ...current, front: dataUrl }))}
                  />
                  <FileField
                    label="Back of ID card"
                    disabled={identitySaving}
                    onFileSelected={(dataUrl) => setIdentityFiles((current) => ({ ...current, back: dataUrl }))}
                  />
                </div>
                {identityError && (
                  <p role="alert" className="status-line status-line--error">
                    {identityError}
                  </p>
                )}
                {identitySaved && <p className="status-line">Verified.</p>}
                <button type="submit" disabled={identitySaving || !identityFiles.front || !identityFiles.back}>
                  {identitySaving ? "Verifying..." : "Upload and verify"}
                </button>
              </form>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
