"use client";

/** Shared segmented control used by the readiness and injury check-in forms.
 * `columns` sets the grid width: 3-up by default; pass 2 for a 2-column (e.g.
 * 2×2) layout so a control with an even option count has no trailing empty cell.
 *
 * `required` marks a control that has no default and must be answered before the
 * form can submit — without it, the only sign of the requirement is a submit
 * button that quietly refuses. `invalid` is the after-the-fact half of the same
 * job: it points at the control the submit attempt actually stopped on. */
export function SegmentGroup<T extends string>({
  label,
  value,
  options,
  onChange,
  columns = 3,
  required = false,
  invalid = false,
}: {
  label: string;
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
  columns?: 2 | 3;
  required?: boolean;
  invalid?: boolean;
}) {
  return (
    <div className="today-field-group">
      <p className="today-field-label">
        {label}
        {required ? <span className="today-field-required">Required</span> : null}
      </p>
      <div
        className={columns === 2 ? "today-segment-row today-segment-row-2col" : "today-segment-row"}
        data-invalid={invalid || undefined}
      >
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
