"use client";

/** Shared segmented control used by the readiness and injury check-in forms. */
export function SegmentGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="today-field-group">
      <p className="today-field-label">{label}</p>
      <div className="today-segment-row">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={option.value === value ? "today-segment today-segment-active" : "today-segment"}
            aria-pressed={option.value === value}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
