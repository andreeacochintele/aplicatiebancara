import { useEffect, useId, useMemo, useRef, useState, type FocusEvent } from "react";

import { COUNTRIES } from "./countries";

interface NationalitySearchSelectProps {
  label: string;
  value: string;
  onChange: (demonym: string) => void;
  required?: boolean;
  placeholder?: string;
}

// Same search-combobox UX as CountrySearchSelect, but for the nationality
// adjective (e.g. "Romanian") rather than the country name, and with no
// flag icon — a nationality isn't a country.
export function NationalitySearchSelect({ label, value, onChange, required, placeholder }: NationalitySearchSelectProps) {
  const listId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState(value);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setQuery(value);
  }, [value]);

  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    // Matches on either the nationality or the country name, since someone
    // may type "Romania" while looking for "Romanian".
    const filtered = term
      ? COUNTRIES.filter(
          (country) => country.demonym.toLowerCase().includes(term) || country.name.toLowerCase().includes(term),
        )
      : COUNTRIES;
    return filtered.slice(0, 50);
  }, [query]);

  function selectNationality(demonym: string) {
    onChange(demonym);
    setQuery(demonym);
    setOpen(false);
  }

  function handleBlur(event: FocusEvent<HTMLDivElement>) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
      setOpen(false);
      // Revert to the last confirmed selection if the typed text isn't an exact match.
      const exact = COUNTRIES.find((country) => country.demonym.toLowerCase() === query.trim().toLowerCase());
      setQuery(exact ? exact.demonym : value);
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
          {matches.length === 0 && <li className="country-select__empty">No matches</li>}
          {matches.map((country) => (
            <li key={country.code}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => selectNationality(country.demonym)}>
                {country.demonym}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
