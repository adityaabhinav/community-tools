import { useEffect, useState } from "react";

export interface ModelItem {
  id: string;
  name: string;
}

/**
 * Dropdown of Spotter-enabled models on the cluster. Fetches /models once,
 * auto-selects the first model, and reports changes to the parent.
 */
export function ModelSelector({
  value,
  onChange,
}: {
  value?: string;
  onChange: (id: string) => void;
}) {
  const [models, setModels] = useState<ModelItem[]>([]);
  const [error, setError] = useState(false);

  // "auto" lets Spotter auto-discover the most relevant dataset per question.
  const AUTO: ModelItem = { id: "auto", name: "Auto (Spotter picks dataset)" };

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/models");
        const data = await res.json();
        setModels(data.models ?? []);
      } catch {
        setError(true);
      }
      if (!value) onChange(AUTO.id); // default to Auto
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) return <span style={labelStyle}>models unavailable</span>;

  return (
    <label style={wrapStyle}>
      <span style={labelStyle}>Model</span>
      <select
        style={selectStyle}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value={AUTO.id}>{AUTO.name}</option>
        {models.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </select>
    </label>
  );
}

const wrapStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  marginLeft: 16,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: "#94a3b8",
};

const selectStyle: React.CSSProperties = {
  padding: "5px 10px",
  borderRadius: 8,
  border: "1px solid #e2e8f0",
  background: "#f8fafc",
  color: "#1e293b",
  fontSize: 13,
  fontWeight: 500,
  cursor: "pointer",
  maxWidth: 260,
};
