import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, apiRequest } from "../../api/apiClient";
import { useAuth } from "../../hooks/useAuth";

type BusinessVerificationStatus = "PENDING_VERIFICATION" | "VERIFIED" | "REJECTED";
type BusinessDocumentStatus = "UPLOADED" | "APPROVED" | "REJECTED";

interface BusinessProfile {
  id: string;
  user_id: string;
  company_name: string;
  representative_name: string | null;
  tax_id: string | null;
  registration_number: string | null;
  verification_status: BusinessVerificationStatus;
  verified_at: string | null;
  rejection_reason: string | null;
  created_at: string;
}

interface BusinessDocument {
  id: string;
  business_profile_id: string;
  document_type: string;
  file_name: string;
  content_type: string | null;
  file_size: number;
  status: BusinessDocumentStatus;
  review_note: string | null;
  uploaded_at: string;
}

interface BusinessDocumentContent {
  id: string;
  file_name: string;
  content_type: string | null;
  content_base64: string;
}

const REQUIRED_DOCUMENT_TYPES = ["REGISTRATION_CERTIFICATE", "ARTICLES_OF_ASSOCIATION", "LEGAL_REPRESENTATIVE_ID"];

function statusClass(status: BusinessVerificationStatus): string {
  if (status === "VERIFIED") return "tag tag--accent";
  if (status === "REJECTED") return "tag tag--warning";
  return "tag tag--neutral";
}

function documentStatusClass(status: BusinessDocumentStatus): string {
  if (status === "APPROVED") return "tag tag--accent";
  if (status === "REJECTED") return "tag tag--warning";
  return "tag tag--outline";
}

function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function openBase64Document(document: BusinessDocumentContent, targetWindow: Window | null) {
  const binary = atob(document.content_base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  const blob = new Blob([bytes], { type: document.content_type ?? "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  if (targetWindow) {
    targetWindow.location.href = url;
  } else {
    const link = window.document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.click();
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export function AdminBusinessVerificationPage() {
  const { t } = useTranslation();
  const { accessToken, logout, user } = useAuth();
  const [profiles, setProfiles] = useState<BusinessProfile[]>([]);
  const [documents, setDocuments] = useState<BusinessDocument[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewingDocumentId, setViewingDocumentId] = useState<string | null>(null);
  const [reviewingDocumentId, setReviewingDocumentId] = useState<string | null>(null);
  const [decidingProfileId, setDecidingProfileId] = useState<string | null>(null);
  const [rejectionDrafts, setRejectionDrafts] = useState<Record<string, string>>({});

  const documentsByProfile = useMemo(() => {
    const groups: Record<string, BusinessDocument[]> = {};
    for (const document of documents) {
      groups[document.business_profile_id] = [...(groups[document.business_profile_id] ?? []), document];
    }
    return groups;
  }, [documents]);
  const pendingProfiles = useMemo(
    () => profiles.filter((profile) => profile.verification_status === "PENDING_VERIFICATION"),
    [profiles],
  );

  async function loadAll(token: string) {
    setIsLoading(true);
    setError(null);
    try {
      const [profileResponse, documentResponse] = await Promise.all([
        apiRequest<BusinessProfile[]>("/business/admin/profiles", { token }),
        apiRequest<BusinessDocument[]>("/business/admin/documents", { token }),
      ]);
      setProfiles(profileResponse);
      setDocuments(documentResponse);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.couldNotLoadApplications"));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (!accessToken || user?.role !== "ADMIN") {
      setIsLoading(false);
      return;
    }
    void loadAll(accessToken);
  }, [accessToken, user?.role]);

  async function viewDocument(document: BusinessDocument) {
    if (!accessToken || viewingDocumentId) return;
    setViewingDocumentId(document.id);
    setError(null);
    const targetWindow = window.open("", "_blank");
    if (targetWindow) {
      targetWindow.document.write(`<p style="font-family: system-ui; padding: 24px;">${t("admin.openingDocument")}</p>`);
      targetWindow.document.close();
    }
    try {
      const content = await apiRequest<BusinessDocumentContent>(`/business/admin/documents/${document.id}/content`, {
        token: accessToken,
      });
      openBase64Document(content, targetWindow);
    } catch (err) {
      targetWindow?.close();
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.couldNotOpenDocument"));
    } finally {
      setViewingDocumentId(null);
    }
  }

  async function reviewDocument(document: BusinessDocument, status: "APPROVED" | "REJECTED") {
    if (!accessToken || reviewingDocumentId) return;
    setReviewingDocumentId(document.id);
    setError(null);
    try {
      const updated = await apiRequest<BusinessDocument>(`/business/admin/documents/${document.id}/review`, {
        method: "PATCH",
        token: accessToken,
        body: { status },
      });
      setDocuments((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.businessVerification.couldNotReviewDocument"));
    } finally {
      setReviewingDocumentId(null);
    }
  }

  async function decideProfile(profile: BusinessProfile, status: "VERIFIED" | "REJECTED") {
    if (!accessToken || decidingProfileId) return;
    const rejectionReason = rejectionDrafts[profile.id]?.trim();
    if (status === "REJECTED" && !rejectionReason) {
      setError(t("admin.businessVerification.rejectionReasonRequired"));
      return;
    }
    setDecidingProfileId(profile.id);
    setError(null);
    try {
      const updated = await apiRequest<BusinessProfile>(`/business/admin/profiles/${profile.id}/decision`, {
        method: "PATCH",
        token: accessToken,
        body: status === "REJECTED" ? { status, rejection_reason: rejectionReason } : { status },
      });
      setProfiles((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      setError(err instanceof ApiError ? err.message : t("admin.businessVerification.couldNotDecideProfile"));
    } finally {
      setDecidingProfileId(null);
    }
  }

  if (user?.role !== "ADMIN") {
    return (
      <section className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("admin.businessVerification.title")}</span>
        </div>
        <div className="card-empty">{t("admin.adminPrivilegesRequired")}</div>
      </section>
    );
  }

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <div className="tile">
        <div className="tile__header">
          <span className="eyebrow">{t("admin.businessVerification.title")}</span>
          <span className="tag tag--neutral">
            {t("admin.businessVerification.pendingCount", { count: pendingProfiles.length })}
          </span>
        </div>
        {error && <p style={{ color: "var(--color-warning)", margin: "0 0 0.85rem" }}>{error}</p>}
        {isLoading && <div className="card-empty">{t("admin.loadingApplications")}</div>}
        {!isLoading && profiles.length === 0 && (
          <div className="card-empty">{t("admin.businessVerification.noProfiles")}</div>
        )}
        {!isLoading &&
          profiles.map((profile) => {
            const profileDocuments = documentsByProfile[profile.id] ?? [];
            const missingRequiredTypes = REQUIRED_DOCUMENT_TYPES.filter(
              (type) => !profileDocuments.some((document) => document.document_type === type),
            );
            const isPending = profile.verification_status === "PENDING_VERIFICATION";
            return (
              <div
                key={profile.id}
                style={{
                  border: "1px solid var(--color-divider)",
                  borderRadius: 10,
                  padding: "0.9rem 1rem",
                  marginTop: "0.75rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
                  <div>
                    <strong>{profile.company_name}</strong>
                    <div style={{ color: "var(--color-text-muted)", fontSize: "0.85rem" }}>
                      {t("admin.businessVerification.taxId")}: {profile.tax_id ?? t("admin.notAvailable")} ·{" "}
                      {t("admin.businessVerification.registrationNumber")}: {profile.registration_number ?? t("admin.notAvailable")}
                    </div>
                  </div>
                  <span className={statusClass(profile.verification_status)}>
                    {t(`businessProfile.verificationStatus.${profile.verification_status}`)}
                  </span>
                </div>

                {profile.rejection_reason && (
                  <p style={{ color: "var(--color-warning)", fontSize: "0.85rem" }}>
                    {t("businessProfile.rejectionReasonLabel")}: {profile.rejection_reason}
                  </p>
                )}

                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", marginTop: "0.6rem" }}>
                  {profileDocuments.length === 0 && (
                    <span style={{ color: "var(--color-text-muted)", fontSize: "0.85rem" }}>
                      {t("admin.businessVerification.noDocumentsUploaded")}
                    </span>
                  )}
                  {profileDocuments.map((document) => (
                    <div
                      key={document.id}
                      style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.85rem" }}
                    >
                      <span>
                        {t(`businessProfile.documentType.${document.document_type}`, { defaultValue: document.document_type })} —{" "}
                        <span title={document.file_name}>{document.file_name}</span> ({formatFileSize(document.file_size)})
                      </span>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                        <span className={documentStatusClass(document.status)}>
                          {t(`businessProfile.documentStatus.${document.status}`)}
                        </span>
                        <button
                          type="button"
                          className="button--ghost"
                          onClick={() => viewDocument(document)}
                          disabled={viewingDocumentId === document.id}
                        >
                          {viewingDocumentId === document.id ? t("admin.opening") : t("admin.view")}
                        </button>
                        {document.status === "UPLOADED" && (
                          <>
                            <button
                              type="button"
                              className="button--ghost"
                              onClick={() => reviewDocument(document, "APPROVED")}
                              disabled={reviewingDocumentId === document.id}
                            >
                              {t("admin.approve")}
                            </button>
                            <button
                              type="button"
                              className="button--ghost"
                              onClick={() => reviewDocument(document, "REJECTED")}
                              disabled={reviewingDocumentId === document.id}
                            >
                              {t("admin.reject")}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {isPending && (
                  <div
                    style={{
                      marginTop: "0.85rem",
                      paddingTop: "0.75rem",
                      borderTop: "1px solid var(--color-divider)",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.6rem",
                    }}
                  >
                    {missingRequiredTypes.length > 0 && (
                      <span className="tag tag--warning" style={{ alignSelf: "flex-start" }}>
                        {t("admin.businessVerification.missingDocuments", { count: missingRequiredTypes.length })}
                      </span>
                    )}
                    <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
                      <button
                        type="button"
                        onClick={() => decideProfile(profile, "VERIFIED")}
                        disabled={decidingProfileId === profile.id}
                      >
                        {t("admin.businessVerification.verifyCompany")}
                      </button>
                      <span style={{ color: "var(--color-text-muted)", fontSize: "0.85rem" }}>{t("admin.or")}</span>
                      <input
                        value={rejectionDrafts[profile.id] ?? ""}
                        onChange={(event) =>
                          setRejectionDrafts((current) => ({ ...current, [profile.id]: event.target.value }))
                        }
                        placeholder={t("admin.businessVerification.rejectionReasonPlaceholder")}
                        style={{ flex: "1 1 240px" }}
                      />
                      <button
                        type="button"
                        className="button--ghost"
                        onClick={() => decideProfile(profile, "REJECTED")}
                        disabled={decidingProfileId === profile.id}
                      >
                        {t("admin.businessVerification.rejectCompany")}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </section>
  );
}
