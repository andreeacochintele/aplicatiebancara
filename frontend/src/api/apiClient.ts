import i18n from "../i18n/config";

// Exported for the few callers that need a raw fetch rather than apiRequest —
// file downloads, which want the Response itself, not parsed JSON.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  token?: string | null;
}

function formatErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return "Validation error";
      })
      .join(" ");
  }
  if (detail && typeof detail === "object" && "msg" in detail) {
    return String((detail as { msg: unknown }).msg);
  }
  return "Request failed";
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, token } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    // Site-wide language preference (LanguageToggle / i18n/config.ts), sent
    // on every request so the AI agents narrate in the same language the
    // rest of the UI is already showing, instead of guessing from message text.
    "X-Locale": i18n.language === "ro" ? "ro" : "en",
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, formatErrorDetail(detail.detail ?? response.statusText));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
