// Whether "Back" can safely step back in history without leaving UNLXCK.
//
// A client-side visit (the document was loaded for a different path) always
// has an in-app page behind it. A full page load only does when it was
// opened from a same-origin page; otherwise (another site, a shared link, a
// new tab) history.back() would leave the app.
export function hasInternalPreviousPage({ documentUrl, currentUrl, referrer }: {
  documentUrl: string | undefined;
  currentUrl: string;
  referrer: string;
}): boolean {
  const current = new URL(currentUrl);
  if (documentUrl && new URL(documentUrl, current).pathname !== current.pathname) {
    return true;
  }
  try {
    return referrer !== "" && new URL(referrer).origin === current.origin;
  } catch {
    return false;
  }
}
