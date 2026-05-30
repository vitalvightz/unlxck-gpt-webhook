const SAFE_DATA_IMAGE_RE = /^data:image\/[a-zA-Z0-9.+\-]+;base64,[A-Za-z0-9+/]+=*$/;

export function isSafeAvatarImageUrl(url: string | null | undefined): boolean {
  if (!url) {
    return false;
  }

  const trimmed = url.trim();
  if (trimmed.startsWith("data:image/")) {
    return SAFE_DATA_IMAGE_RE.test(trimmed);
  }

  try {
    const parsed = new URL(trimmed);
    return parsed.protocol === "https:";
  } catch {
    return false;
  }
}
