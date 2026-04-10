import zxcvbn from "zxcvbn";

export type PasswordStrengthTone = "empty" | "red" | "amber" | "green";

export type PasswordStrength = {
  feedback: string;
  isAcceptable: boolean;
  label: string;
  minLengthMet: boolean;
  score: 0 | 1 | 2 | 3 | 4;
  tone: PasswordStrengthTone;
};

function normalizeUserInputs(values: Array<string | null | undefined>): string[] {
  return values
    .flatMap((value) => {
      const normalized = String(value ?? "").trim().toLowerCase();
      if (!normalized) {
        return [];
      }

      const parts = normalized.split(/[^a-z0-9]+/).filter(Boolean);
      const collapsed = normalized.replace(/[^a-z0-9]+/g, "");
      return collapsed && !parts.includes(collapsed) ? [...parts, collapsed] : parts;
    })
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);
}

function containsUserInputFragment(password: string, userInputs: string[]): boolean {
  const normalizedPassword = password.toLowerCase().replace(/[^a-z0-9]+/g, "");
  return userInputs.some((value) => value.length >= 4 && normalizedPassword.includes(value));
}

function buildFeedback(
  result: zxcvbn.ZXCVBNResult,
  minLengthMet: boolean,
  hasUserInputMatch: boolean,
): string {
  if (!minLengthMet) {
    return "Use at least 8 characters.";
  }
  if (hasUserInputMatch) {
    return "Avoid using your name or email in your password.";
  }

  const suggestions = result.feedback.suggestions.filter(Boolean);
  if (result.feedback.warning) {
    return [result.feedback.warning, ...suggestions].join(" ");
  }
  if (suggestions.length) {
    return suggestions.join(" ");
  }
  if (result.score >= 3) {
    return "Strong password.";
  }
  return "Add another word, symbol, or uncommon phrase.";
}

export function evaluatePasswordStrength(
  password: string,
  options?: {
    email?: string | null;
    fullName?: string | null;
  },
): PasswordStrength {
  const trimmedPassword = password ?? "";
  const userInputs = normalizeUserInputs([options?.fullName, options?.email]);
  if (!trimmedPassword) {
    return {
      score: 0,
      tone: "empty",
      label: "Too weak",
      feedback: "Use at least 8 characters.",
      minLengthMet: false,
      isAcceptable: false,
    };
  }

  const result = zxcvbn(
    trimmedPassword,
    userInputs,
  );
  const minLengthMet = trimmedPassword.length >= 8;
  const hasUserInputMatch = containsUserInputFragment(trimmedPassword, userInputs);
  const tone: PasswordStrengthTone = !minLengthMet || hasUserInputMatch || result.score <= 1
    ? "red"
    : result.score === 2
      ? "amber"
      : "green";

  return {
    score: result.score,
    tone,
    label: tone === "green" ? "Strong" : tone === "amber" ? "Okay" : "Too weak",
    feedback: buildFeedback(result, minLengthMet, hasUserInputMatch),
    minLengthMet,
    isAcceptable: tone === "amber" || tone === "green",
  };
}
