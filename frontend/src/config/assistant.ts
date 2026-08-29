import type { OrchestratorIntent } from "../types";

/** The assistant's display name — the single place this is defined, so
 * AssistantPage.tsx (hero copy) never hardcodes it inline. */
export const ASSISTANT_NAME = "Nova";

export interface AssistantQuickAction {
  intent: OrchestratorIntent;
  labelKey: string;
  /** Inserted into the chat input when clicked — the user still reviews/
   * edits and sends it themselves, same as any other message. Always
   * English: it's sent to the assistant as a real chat message, not UI
   * copy, so it isn't translated with the rest of the page. */
  starterPrompt: string;
}

export const ASSISTANT_QUICK_ACTIONS: AssistantQuickAction[] = [
  { intent: "personal_finance", labelKey: "assistant.quickActionPersonalFinance", starterPrompt: "How much did I spend this month?" },
  { intent: "credit", labelKey: "assistant.quickActionCredit", starterPrompt: "What's my credit score?" },
  { intent: "support", labelKey: "assistant.quickActionSupport", starterPrompt: "How do budgets work in this app?" },
  { intent: "action", labelKey: "assistant.quickActionSendMoney", starterPrompt: "Trimite 50 RON lui " },
];
