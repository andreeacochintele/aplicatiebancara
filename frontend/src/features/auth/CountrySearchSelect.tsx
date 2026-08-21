import { useEffect, useId, useMemo, useRef, useState, type FocusEvent } from "react";

import { COUNTRIES, countryFlagEmoji } from "./countries";

interface CountrySearchSelectProps {
  label: string;
  value: string;
  onChange: (name: string) => void;
  required?: boolean;
  placeholder?: string;
}

export function CountrySearchSelect({ label, value, onChange, required, placeholder }: CountrySearchSelectProps) {
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
          {matches.length === 0 && <li className="country-select__empty">No matches</li>}
          {matches.map((country) => (
            <li key={country.code}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => selectCountry(country.name)}>
                <span className="country-select__flag">{countryFlagEmoji(country.code)}</span>
                {country.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
