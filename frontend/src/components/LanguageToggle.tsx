import { useTranslation } from "react-i18next";

const NEXT_LANGUAGE: Record<string, "en" | "ro"> = { en: "ro", ro: "en" };
const FLAG_CODE: Record<string, string> = { en: "gb", ro: "ro" };

export function LanguageToggle() {
  const { i18n, t } = useTranslation();
  const current = i18n.language === "ro" ? "ro" : "en";
  const next = NEXT_LANGUAGE[current];

  return (
    <button
      type="button"
      aria-label={t("language.switchTo", { language: t(`language.${next === "ro" ? "romanian" : "english"}`) })}
      title={t("language.switchTo", { language: t(`language.${next === "ro" ? "romanian" : "english"}`) })}
      onClick={() => i18n.changeLanguage(next)}
      className="language-toggle"
    >
      <span className={`fi fi-${FLAG_CODE[current]} language-toggle__flag`} aria-hidden="true" />
      <span className="language-toggle__code">{current.toUpperCase()}</span>
    </button>
  );
}
