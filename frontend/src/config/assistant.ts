import type { OrchestratorIntent } from "../types";

/** The assistant's display name — the single place this is defined, so
 * AssistantPage.tsx (hero copy) never hardcodes it inline. */
export const ASSISTANT_NAME = "Nova";

export interface AssistantQuickAction {
  intent: OrchestratorIntent;
  label: string;
  /** Inserted into the chat input when clicked — the user still reviews/
   * edits and sends it themselves, same as any other message. */
  starterPrompt: string;
}

export const ASSISTANT_QUICK_ACTIONS: AssistantQuickAction[] = [
  { intent: "personal_finance", label: "Personal Finance", starterPrompt: "How much did I spend this month?" },
  { intent: "credit", label: "Credit", starterPrompt: "What's my credit score?" },
  { intent: "support", label: "Support", starterPrompt: "How do budgets work in this app?" },
  { intent: "action", label: "Trimite bani", starterPrompt: "Trimite 50 RON lui " },
];
