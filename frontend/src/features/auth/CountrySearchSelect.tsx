import { useEffect, useId, useMemo, useRef, useState, type FocusEvent } from "react";
import { useTranslation } from "react-i18next";

import { COUNTRIES } from "./countries";

interface CountrySearchSelectProps {
  label: string;
  value: string;
  onChange: (name: string) => void;
  required?: boolean;
  placeholder?: string;
}

export function CountrySearchSelect({ label, value, onChange, required, placeholder }: CountrySearchSelectProps) {
  const { t } = useTranslation();
  const listId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState(value);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setQuery(value);
  }, [value]);

  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    const filtered = term ? COUNTRIES.filter((country) => country.name.toLowerCase().includes(term)) : COUNTRIES;
    return filtered.slice(0, 50);
  }, [query]);

  function selectCountry(name: string) {
    onChange(name);
    setQuery(name);
    setOpen(false);
  }

  function handleBlur(event: FocusEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setOpen(false);
      // Revert to the last confirmed selection if the typed text isn't an exact match.
      const exact = COUNTRIES.find((country) => country.name.toLowerCase() === query.trim().toLowerCase());
      setQuery(exact ? exact.name : value);
    }
  }

  return (
    <div className="country-select" ref={containerRef} onBlur={handleBlur}>
      <label>
        {label}
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          autoComplete="off"
          value={query}
          required={required}
          placeholder={placeholder}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
        />
      </label>
      {open && (
        <ul id={listId} role="listbox" className="country-select__list">
          {matches.length === 0 && <li className="country-select__empty">{t("common.noMatches")}</li>}
          {matches.map((country) => (
            <li key={country.code}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => selectCountry(country.name)}>
                <span className={`fi fi-${country.code.toLowerCase()} country-select__flag`} aria-hidden="true" />
                {country.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
