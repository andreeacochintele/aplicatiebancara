import { useEffect, useState, type ChangeEvent } from "react";

const OTHER_VALUE = "__other__";

interface DropdownWithOtherProps {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  required?: boolean;
}

export function DropdownWithOther({ label, value, options, onChange, required }: DropdownWithOtherProps) {
  const [otherMode, setOtherMode] = useState(() => value !== "" && !options.includes(value));

  useEffect(() => {
    // Only switch INTO "other" mode automatically (e.g. once the saved profile loads with
    // a custom value); never switch back out from under someone actively typing.
    if (!otherMode && value !== "" && !options.includes(value)) {
      setOtherMode(true);
    }
  }, [value, options, otherMode]);

  function handleSelectChange(event: ChangeEvent<HTMLSelectElement>) {
    const next = event.target.value;
    if (next === OTHER_VALUE) {
      setOtherMode(true);
      onChange("");
    } else {
      setOtherMode(false);
      onChange(next);
    }
  }

  return (
    <>
      <label>
        {label}
        <select value={otherMode ? OTHER_VALUE : value} required={required} onChange={handleSelectChange}>
          <option value="">Select...</option>
          {options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
          <option value={OTHER_VALUE}>Other</option>
        </select>
      </label>
      {otherMode && (
        <label>
          {`${label} (please specify)`}
          <input value={value} onChange={(e) => onChange(e.target.value)} required={required} />
        </label>
      )}
    </>
  );
}
