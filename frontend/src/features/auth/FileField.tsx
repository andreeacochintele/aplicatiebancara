import { useState, type ChangeEvent } from "react";

interface FileFieldProps {
  label: string;
  onFileSelected: (dataUrl: string) => void;
  disabled?: boolean;
}

export function FileField({ label, onFileSelected, disabled }: FileFieldProps) {
  const [fileName, setFileName] = useState<string | null>(null);

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = () => onFileSelected(String(reader.result));
    reader.readAsDataURL(file);
  }

  return (
    <label>
      {label}
      <input type="file" accept="image/*" onChange={handleChange} disabled={disabled} />
      {fileName && <small className="field-hint">{fileName}</small>}
    </label>
  );
}
