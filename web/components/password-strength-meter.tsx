"use client";

import type { PasswordStrength } from "@/lib/password-strength";

type PasswordStrengthMeterProps = {
  strength: PasswordStrength;
};

function getActiveSegments(strength: PasswordStrength): number {
  if (strength.tone === "green") {
    return 3;
  }
  if (strength.tone === "amber") {
    return 2;
  }
  if (strength.tone === "red") {
    return 1;
  }
  return 0;
}

export function PasswordStrengthMeter({ strength }: PasswordStrengthMeterProps) {
  const activeSegments = getActiveSegments(strength);

  return (
    <div className="password-strength" aria-live="polite">
      <div className="password-strength-header">
        <span className="password-strength-title">Password strength</span>
        <span className={`password-strength-chip password-strength-chip-${strength.tone}`.trim()}>
          {strength.label}
        </span>
      </div>
      <div
        className="password-strength-bar"
        role="img"
        aria-label={`Password strength ${strength.label.toLowerCase()}`}
      >
        {[0, 1, 2].map((index) => {
          const isActive = index < activeSegments;
          return (
            <span
              key={index}
              className={`password-strength-segment${isActive ? ` password-strength-segment-${strength.tone}` : ""}`.trim()}
            />
          );
        })}
      </div>
      <p className={`password-strength-message password-strength-message-${strength.tone}`.trim()}>
        {strength.feedback}
      </p>
    </div>
  );
}
