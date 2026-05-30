const SAFE_DATA_IMAGE_RE = /^data:image\/[a-zA-Z0-9.+\-]+;base64,[A-Za-z0-9+/]+=*$/;

export function isSafeAvatarImageUrl(url: string): boolean {
  if (url.startsWith("data:image/")) {
    return SAFE_DATA_IMAGE_RE.test(url);
  }

  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:";
  } catch {
    return false;
  }
}
