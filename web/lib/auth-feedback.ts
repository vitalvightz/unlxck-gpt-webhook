type AuthErrorLike = {
  code?: string | null;
  message?: string | null;
  name?: string | null;
  status?: number | null;
};

export const AUTH_FEEDBACK = {
  connectionFailure: "UNLXCK could not connect. Try again.",
  incorrectCredentials: "Email or password is incorrect.",
  magicLinkFailure: "UNLXCK could not send a sign-in link. Try again.",
  magicLinkSent: "Sign-in link sent. Check your inbox.",
  passwordResetFailure: "UNLXCK could not send a reset link. Try again.",
  signInFailure: "UNLXCK could not sign you in. Try again.",
  tooManyAttempts: "Too many attempts. Try again shortly.",
} as const;

function isRateLimitError(error: AuthErrorLike): boolean {
  return error.status === 429 || Boolean(error.code?.toLowerCase().includes("rate_limit"));
}

function isConnectionError(error: AuthErrorLike): boolean {
  return (
    error.name === "AuthRetryableFetchError" ||
    error.status === 0 ||
    error.code?.toLowerCase() === "request_timeout"
  );
}

export function getLoginErrorMessage(error: AuthErrorLike): string {
  if (isRateLimitError(error)) {
    return AUTH_FEEDBACK.tooManyAttempts;
  }

  if (isConnectionError(error)) {
    return AUTH_FEEDBACK.connectionFailure;
  }

  const code = error.code?.toLowerCase();
  const providerMessage = error.message?.toLowerCase() ?? "";
  if (
    code === "invalid_credentials" ||
    providerMessage.includes("invalid login credentials") ||
    providerMessage.includes("invalid credentials")
  ) {
    return AUTH_FEEDBACK.incorrectCredentials;
  }

  return AUTH_FEEDBACK.signInFailure;
}

/**
 * Rate limits and connection failures read the same whatever the athlete was
 * trying to send, so only the last-resort message differs per action.
 */
function getEmailSendErrorMessage(error: AuthErrorLike, fallback: string): string {
  if (isRateLimitError(error)) {
    return AUTH_FEEDBACK.tooManyAttempts;
  }

  return isConnectionError(error) ? AUTH_FEEDBACK.connectionFailure : fallback;
}

export function getMagicLinkErrorMessage(error: AuthErrorLike): string {
  return getEmailSendErrorMessage(error, AUTH_FEEDBACK.magicLinkFailure);
}

export function getPasswordResetErrorMessage(error: AuthErrorLike): string {
  return getEmailSendErrorMessage(error, AUTH_FEEDBACK.passwordResetFailure);
}
