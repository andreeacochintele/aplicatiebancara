import { apiRequest } from "../../api/apiClient";
import type {
  OnboardingStep2Payload,
  OnboardingStep4Payload,
  RegisterPayload,
  User,
  UserFullProfile,
} from "../../types";

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
}

export interface AuthResponse {
  user: User;
  tokens: AuthTokens;
}

export function registerUser(payload: RegisterPayload) {
  return apiRequest<AuthResponse>("/auth/register", {
    method: "POST",
    body: payload,
  });
}

export function loginUser(email: string, password: string) {
  return apiRequest<AuthResponse>("/auth/login", {
    method: "POST",
    body: { email, password },
  });
}

export function getMyFullProfile(token: string) {
  return apiRequest<UserFullProfile>("/users/me/profile", { token });
}

export function updateOnboardingStep2(token: string, payload: OnboardingStep2Payload) {
  return apiRequest<UserFullProfile>("/users/me/onboarding/step-2", {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function createIdentityDocumentPlaceholder(token: string) {
  return apiRequest<UserFullProfile>("/users/me/onboarding/step-3/identity-document-placeholder", {
    method: "POST",
    token,
  });
}

export function updateOnboardingStep4(token: string, payload: OnboardingStep4Payload) {
  return apiRequest<UserFullProfile>("/users/me/onboarding/step-4", {
    method: "PATCH",
    token,
    body: payload,
  });
}

export function skipOnboardingStep4(token: string) {
  return apiRequest<UserFullProfile>("/users/me/onboarding/step-4/skip", {
    method: "POST",
    token,
  });
}
