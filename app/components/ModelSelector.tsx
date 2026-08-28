"use client";

type ModelSelectorProps = {
  label: string;
  value: string;
  models: string[];
  loading: boolean;
  onChange: (value: string) => void;
};

function inputId(label: string) {
  return `${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-model`;
}

export function ModelSelector({ label, value, models, loading, onChange }: ModelSelectorProps) {
  const id = inputId(label);
  const options = Array.from(new Set(models.filter(Boolean)));

  return (
    <label className="block min-w-0">
      <span className="font-mono-label text-fog/65">{label}</span>
      <input
        id={id}
        list={`${id}-options`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        maxLength={160}
        placeholder="Type or discover a model id"
        className="mt-2 h-11 w-full min-w-0 rounded-xl border border-white/10 bg-black/20 px-3 text-sm text-white outline-none transition-colors hover:border-white/20 focus:border-lime/50"
      />
      <datalist id={`${id}-options`}>
        {options.map((model) => <option key={model} value={model} />)}
      </datalist>
      <span className="mt-1 block truncate text-[11px] text-fog/50">
        {loading ? "Discovering models..." : options.length > 0 ? `${options.length} discovered model(s)` : "Enter a model id manually or use Discover"}
      </span>
    </label>
  );
}
