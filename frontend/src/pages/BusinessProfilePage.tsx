import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { apiRequest, ApiError } from "../api/apiClient";
import { useAuth } from "../hooks/useAuth";

type BusinessVerificationStatus = "PENDING_VERIFICATION" | "VERIFIED" | "REJECTED";
type BusinessDocumentType =
  | "REGISTRATION_CERTIFICATE"
  | "ARTICLES_OF_ASSOCIATION"
  | "LEGAL_REPRESENTATIVE_ID"
  | "PROOF_OF_ADDRESS";
type BusinessDocumentStatus = "UPLOADED" | "APPROVED" | "REJECTED";

interface BusinessProfile {
  id: string;
  user_id: string;
  company_name: string;
  representative_name: string | null;
  tax_id: string | null;
  registration_number: string | null;
  business_category: string | null;
  is_active: boolean;
  verification_status: BusinessVerificationStatus;
  verified_at: string | null;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
}

interface BusinessDocument {
  id: string;
  business_profile_id: string;
  document_type: BusinessDocumentType;
  file_name: string;
  file_size: number;
  status: BusinessDocumentStatus;
  review_note: string | null;
  uploaded_at: string;
}

const REQUIRED_DOCUMENT_TYPES: BusinessDocumentType[] = [
  "REGISTRATION_CERTIFICATE",
  "ARTICLES_OF_ASSOCIATION",
  "LEGAL_REPRESENTATIVE_ID",
];
const OPTIONAL_DOCUMENT_TYPES: BusinessDocumentType[] = ["PROOF_OF_ADDRESS"];

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

interface ProfileFormState {
  company_name: string;
  representative_name: string;
  tax_id: string;
  registration_number: string;
  business_category: string;
}

interface CuiLookupResult {
  cui: string;
  company_name: string;
  registration_number: string | null;
  address: string | null;
  is_active: boolean;
}

const EMPTY_FORM: ProfileFormState = {
  company_name: "",
  representative_name: "",
  tax_id: "",
  registration_number: "",
  business_category: "",
};

function toFormState(profile: BusinessProfile): ProfileFormState {
  return {
    company_name: profile.company_name,
    representative_name: profile.representative_name ?? "",
    tax_id: profile.tax_id ?? "",
    registration_number: profile.registration_number ?? "",
    business_category: profile.business_category ?? "",
  };
}

export function BusinessProfilePage() {
  const { t } = useTranslation();
  const { user, accessToken } = useAuth();
  const [profiles, setProfiles] = useState<BusinessProfile[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<ProfileFormState>(EMPTY_FORM);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [cuiQuery, setCuiQuery] = useState("");
  const [cuiLookupBusy, setCuiLookupBusy] = useState(false);
  const [cuiLookupError, setCuiLookupError] = useState<string | null>(null);
  const [cuiLookupInactive, setCuiLookupInactive] = useState(false);
  const [cuiVerified, setCuiVerified] = useState(false);
  const [documents, setDocuments] = useState<BusinessDocument[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [uploadingType, setUploadingType] = useState<BusinessDocumentType | null>(null);
  const [documentError, setDocumentError] = useState<string | null>(null);

  const isBusiness = user?.user_type === "BUSINESS";
  const isNew = selectedId === null;
  const selectedProfile = profiles.find((p) => p.id === selectedId) ?? null;
  // Identity fields lock the moment a profile is saved, not just for the
  // browser session that ran the CUI lookup - editing a previously-added
  // company must never let its verified identity drift out from under it.
  const identityLocked = cuiVerified || !isNew;

  useEffect(() => {
    if (!isBusiness || !accessToken) return;
    loadProfiles();
  }, [isBusiness, accessToken]);

  useEffect(() => {
    if (!accessToken || !selectedId) {
      setDocuments([]);
      return;
    }
    void loadDocuments(accessToken, selectedId);
  }, [accessToken, selectedId]);

  async function loadProfiles() {
    if (!accessToken) return;
    try {
      const list = await apiRequest<BusinessProfile[]>("/business/profiles", { token: accessToken });
      setProfiles(list);
      const active = list.find((p) => p.is_active) ?? list[0] ?? null;
      if (active) {
        setSelectedId(active.id);
        setForm(toFormState(active));
      }
    } finally {
      setLoaded(true);
    }
  }

  async function loadDocuments(token: string, profileId: string) {
    setDocumentsLoading(true);
    try {
      const list = await apiRequest<BusinessDocument[]>(`/business/profiles/${profileId}/documents`, { token });
      setDocuments(list);
    } catch {
      setDocuments([]);
    } finally {
      setDocumentsLoading(false);
    }
  }

  async function uploadDocument(documentType: BusinessDocumentType, file: File) {
    if (!accessToken || !selectedId || uploadingType) return;
    setUploadingType(documentType);
    setDocumentError(null);
    try {
      const content_base64 = await readFileAsBase64(file);
      await apiRequest<BusinessDocument>(`/business/profiles/${selectedId}/documents`, {
        method: "POST",
        token: accessToken,
        body: {
          document_type: documentType,
          file_name: file.name,
          content_type: file.type || null,
          file_size: file.size,
          content_base64,
        },
      });
      await loadDocuments(accessToken, selectedId);
    } catch (err) {
      setDocumentError(err instanceof ApiError ? err.message : t("businessProfile.documentUploadFailed"));
    } finally {
      setUploadingType(null);
    }
  }

  if (!isBusiness) {
    return (
      <section className="tile">
        <p>{t("businessProfile.onlyForBusiness")}</p>
      </section>
    );
  }
  if (!loaded) return null;

  function selectProfile(profile: BusinessProfile) {
    setSelectedId(profile.id);
    setForm(toFormState(profile));
    setSaved(false);
    setError(null);
    setCuiVerified(false);
  }

  function startNewCompany() {
    setSelectedId(null);
    setForm(EMPTY_FORM);
    setSaved(false);
    setError(null);
    setCuiVerified(false);
  }

  async function activate(profile: BusinessProfile) {
    if (!accessToken || profile.is_active) return;
    setError(null);
    try {
      await apiRequest(`/business/profiles/${profile.id}/activate`, { method: "PUT", token: accessToken });
      await loadProfiles();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("businessProfile.couldNotSwitchCompany"));
    }
  }

  async function lookupCui() {
    if (!accessToken || !cuiQuery.trim() || cuiLookupBusy) return;
    setCuiLookupBusy(true);
    setCuiLookupError(null);
    setCuiLookupInactive(false);
    try {
      const result = await apiRequest<CuiLookupResult>(
        `/business/lookup-cui/${encodeURIComponent(cuiQuery.trim())}`,
        { token: accessToken },
      );
      setForm((prev) => ({
        ...prev,
        company_name: result.company_name || prev.company_name,
        registration_number: result.registration_number ?? prev.registration_number,
        tax_id: result.cui,
      }));
      setCuiLookupInactive(!result.is_active);
      setCuiVerified(true);
      setSaved(false);
    } catch (err) {
      setCuiLookupError(err instanceof ApiError ? err.message : t("businessProfile.cuiLookupFailed"));
    } finally {
      setCuiLookupBusy(false);
    }
  }

  async function save() {
    if (!accessToken || !form.company_name.trim()) return;
    setError(null);
    setSaved(false);
    setBusy(true);
    const body = {
      company_name: form.company_name,
      representative_name: form.representative_name || null,
      tax_id: form.tax_id || null,
      registration_number: form.registration_number || null,
      business_category: form.business_category || null,
    };
    try {
      if (isNew) {
        const created = await apiRequest<BusinessProfile>("/business/profiles", {
          method: "POST",
          token: accessToken,
          body,
        });
        await loadProfiles();
        setSelectedId(created.id);
      } else {
        await apiRequest<BusinessProfile>(`/business/profiles/${selectedId}`, {
          method: "PUT",
          token: accessToken,
          body,
        });
        await loadProfiles();
      }
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("businessProfile.couldNotSaveProfile"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {profiles.length > 0 && (
        <div className="tile" style={{ maxWidth: 480 }}>
          <div className="tile__header">
            <span className="eyebrow">{t("businessProfile.yourCompanies")}</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {profiles.map((profile) => (
              <div
                key={profile.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "0.5rem 0.75rem",
                  borderRadius: 8,
                  border: "1px solid var(--color-divider)",
                  background: profile.id === selectedId ? "var(--color-surface-raised)" : "transparent",
                  cursor: "pointer",
                }}
                onClick={() => selectProfile(profile)}
              >
                <div>
                  <strong>{profile.company_name}</strong>
                  {profile.is_active && <span className="tag tag--accent" style={{ marginLeft: "0.5rem" }}>{t("businessProfile.active")}</span>}
                </div>
                {!profile.is_active && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      activate(profile);
                    }}
                  >
                    {t("businessProfile.switchToCompany")}
                  </button>
                )}
              </div>
            ))}
          </div>
          <div style={{ marginTop: "0.75rem" }}>
            <button type="button" onClick={startNewCompany}>
              {t("businessProfile.addAnotherCompany")}
            </button>
          </div>
        </div>
      )}

      <div className="tile" style={{ maxWidth: 480 }}>
        <div className="tile__header">
          <span className="eyebrow">{isNew ? t("businessProfile.newCompany") : t("businessProfile.editCompany")}</span>
          {selectedProfile && (
            <span
              className={`tag ${
                selectedProfile.verification_status === "VERIFIED"
                  ? "tag--accent"
                  : selectedProfile.verification_status === "REJECTED"
                    ? "tag--warning"
                    : "tag--neutral"
              }`}
            >
              {t(`businessProfile.verificationStatus.${selectedProfile.verification_status}`)}
            </span>
          )}
        </div>
        <p style={{ color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
          {t("businessProfile.activeCompanyNote")}
        </p>
        {selectedProfile?.verification_status === "REJECTED" && selectedProfile.rejection_reason && (
          <p role="alert" style={{ color: "var(--color-negative)", fontSize: "0.9rem" }}>
            {t("businessProfile.rejectionReasonLabel")}: {selectedProfile.rejection_reason}
          </p>
        )}
        {identityLocked ? (
          <p style={{ color: "var(--color-text-muted)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
            {t("businessProfile.cuiVerifiedNote")}
          </p>
        ) : (
          <div
            style={{
              display: "flex",
              gap: "0.5rem",
              alignItems: "flex-end",
              marginTop: "0.5rem",
              padding: "0.75rem",
              borderRadius: 8,
              border: "1px solid var(--color-divider)",
            }}
          >
            <label style={{ flex: 1 }}>
              {t("businessProfile.cuiLookupLabel")}
              <input
                type="text"
                value={cuiQuery}
                onChange={(e) => setCuiQuery(e.target.value)}
                placeholder="RO12345678"
              />
            </label>
            <button type="button" onClick={lookupCui} disabled={cuiLookupBusy || !cuiQuery.trim()}>
              {cuiLookupBusy ? t("businessProfile.cuiLookupBusy") : t("businessProfile.cuiLookupButton")}
            </button>
          </div>
        )}
        {cuiLookupError && (
          <p role="alert" style={{ color: "var(--color-negative)", fontSize: "0.9rem" }}>
            {cuiLookupError}
          </p>
        )}
        {cuiLookupInactive && (
          <p style={{ color: "var(--color-warning)", fontSize: "0.9rem" }}>{t("businessProfile.cuiLookupInactive")}</p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "0.5rem" }}>
          <label>
            {t("businessProfile.companyName")}
            <input
              type="text"
              value={form.company_name}
              onChange={(e) => setForm({ ...form, company_name: e.target.value })}
              placeholder="Acme SRL"
              disabled={identityLocked}
            />
          </label>
          <label>
            {t("businessProfile.representative")}
            <input
              type="text"
              value={form.representative_name}
              onChange={(e) => setForm({ ...form, representative_name: e.target.value })}
              placeholder={t("businessProfile.representativePlaceholder")}
            />
          </label>
          <label>
            {t("businessProfile.taxId")}
            <input
              type="text"
              value={form.tax_id}
              onChange={(e) => setForm({ ...form, tax_id: e.target.value })}
              placeholder="RO12345678"
              disabled={identityLocked}
            />
          </label>
          <label>
            {t("businessProfile.registrationNumber")}
            <input
              type="text"
              value={form.registration_number}
              onChange={(e) => setForm({ ...form, registration_number: e.target.value })}
              placeholder="J40/1234/2024"
              disabled={identityLocked}
            />
          </label>
          <label>
            {t("businessProfile.businessCategory")}
            <input
              type="text"
              value={form.business_category}
              onChange={(e) => setForm({ ...form, business_category: e.target.value })}
              placeholder="Retail"
            />
          </label>
        </div>
        <div style={{ marginTop: "1rem" }}>
          <button onClick={save} disabled={busy || !form.company_name.trim()}>
            {busy ? t("businessProfile.saving") : isNew ? t("businessProfile.createCompany") : t("businessProfile.save")}
          </button>
        </div>
        {saved && <p style={{ color: "var(--color-positive)" }}>{t("businessProfile.saved")}</p>}
        {error && <p role="alert">{error}</p>}
      </div>

      {!isNew && (
        <div className="tile" style={{ maxWidth: 480 }}>
          <div className="tile__header">
            <span className="eyebrow">{t("businessProfile.documentsTitle")}</span>
            {documentsLoading && <span className="tag tag--neutral">{t("businessBulkTransfer.loading")}</span>}
          </div>
          <p style={{ color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
            {t("businessProfile.documentsNote")}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", marginTop: "0.5rem" }}>
            {[...REQUIRED_DOCUMENT_TYPES, ...OPTIONAL_DOCUMENT_TYPES].map((documentType) => {
              const uploaded = documents.filter((doc) => doc.document_type === documentType);
              const isOptional = OPTIONAL_DOCUMENT_TYPES.includes(documentType);
              return (
                <div
                  key={documentType}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.35rem",
                    padding: "0.6rem 0.75rem",
                    borderRadius: 8,
                    border: "1px solid var(--color-divider)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <strong style={{ fontSize: "0.9rem" }}>
                      {t(`businessProfile.documentType.${documentType}`)}
                      {isOptional && (
                        <span style={{ color: "var(--color-text-muted)", fontWeight: 400 }}>
                          {" "}
                          ({t("businessProfile.optional")})
                        </span>
                      )}
                    </strong>
                    <label className="button--ghost" style={{ cursor: "pointer" }}>
                      {uploadingType === documentType ? t("businessProfile.uploading") : t("businessProfile.uploadDocument")}
                      <input
                        type="file"
                        accept=".pdf,.png,.jpg,.jpeg"
                        style={{ display: "none" }}
                        disabled={uploadingType !== null}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          e.target.value = "";
                          if (file) void uploadDocument(documentType, file);
                        }}
                      />
                    </label>
                  </div>
                  {uploaded.length === 0 ? (
                    <span style={{ color: "var(--color-text-muted)", fontSize: "0.8rem" }}>
                      {t("businessProfile.noDocumentYet")}
                    </span>
                  ) : (
                    uploaded.map((doc) => (
                      <div key={doc.id} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
                        <span title={doc.file_name}>{doc.file_name}</span>
                        <span
                          className={`tag ${
                            doc.status === "APPROVED"
                              ? "tag--accent"
                              : doc.status === "REJECTED"
                                ? "tag--warning"
                                : "tag--neutral"
                          }`}
                        >
                          {t(`businessProfile.documentStatus.${doc.status}`)}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              );
            })}
          </div>
          {documentError && (
            <p role="alert" style={{ color: "var(--color-negative)", fontSize: "0.9rem", marginTop: "0.5rem" }}>
              {documentError}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
