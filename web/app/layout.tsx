import type { ReactNode } from "react";
import type { Metadata } from "next";
import type { Viewport } from "next";
import { headers } from "next/headers";

import { AppNav } from "@/components/app-nav";
import { AuthProvider } from "@/components/auth-provider";
import { GenerationStatusShell } from "@/components/generation-status-shell";
import { PwaRegister } from "@/components/pwa-register";
import { ToastProvider } from "@/components/toast-provider";
import { SAFETY_DISCLAIMER_SHORT, SAFETY_DISCLAIMER_TIGHT } from "@/lib/safety-copy";
import { APPEARANCE_STORAGE_KEY } from "@/lib/types";
import "./globals.css";

// Runs synchronously in <head> before first paint: restore the athlete's saved
// appearance mode so a light-theme user never sees the dark SSR default flash to
// light after hydration. Kept dependency-free so it can be inlined as a string.
const THEME_INIT_SCRIPT = `(function(){try{var m=localStorage.getItem(${JSON.stringify(
  APPEARANCE_STORAGE_KEY,
)});if(m==="light"||m==="dark"){var d=document.documentElement;d.dataset.theme=m;d.style.colorScheme=m;}}catch(e){}})();`;

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "UNLXCK Athlete Control Room",
  description: "Athlete-first fight camp planning on the web.",
  applicationName: "UNLXCK",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/icons/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/icons/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/icon-192x192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  appleWebApp: {
    capable: true,
    title: "UNLXCK",
    statusBarStyle: "black-translucent",
  },
  formatDetection: {
    address: false,
    email: false,
    telephone: false,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0b" },
    { media: "(prefers-color-scheme: light)", color: "#faf7f2" },
  ],
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  // The per-request CSP (set in proxy.ts) uses a nonce + 'strict-dynamic', so the
  // inline theme-init script must carry that nonce or it is blocked and the flash
  // returns. Undefined when no CSP is present — the attribute is simply omitted.
  //
  // Only accept a value matching the shape proxy.ts generates (btoa of a random
  // UUID -> 48-char unpadded base64). On routes the middleware excludes there is
  // no CSP, but a client could still supply an arbitrary x-nonce header; this
  // guard means such a value is never reflected into the page as a nonce.
  const rawNonce = (await headers()).get("x-nonce");
  const nonce = rawNonce && /^[A-Za-z0-9+/]{48}$/.test(rawNonce) ? rawNonce : undefined;
  const pwaBuildVersion =
    process.env.VERCEL_GIT_COMMIT_SHA ??
    process.env.VERCEL_DEPLOYMENT_ID ??
    process.env.VERCEL_URL ??
    "local";
  return (
    <html lang="en" data-theme="dark" style={{ colorScheme: "dark" }} suppressHydrationWarning>
      <head>
        <script nonce={nonce} suppressHydrationWarning dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <AuthProvider>
          <ToastProvider>
            <PwaRegister buildVersion={pwaBuildVersion}>
              <GenerationStatusShell>
                <div className="app-shell">
                  <AppNav />
                  <div className="app-content">
                    <main className="app-main">
                      <div className="page">{children}</div>
                    </main>
                    <footer className="app-safety-footer" role="contentinfo">
                      <span className="app-safety-footer-wide">{SAFETY_DISCLAIMER_SHORT}</span>
                      <span className="app-safety-footer-tight">{SAFETY_DISCLAIMER_TIGHT}</span>
                    </footer>
                  </div>
                </div>
              </GenerationStatusShell>
            </PwaRegister>
          </ToastProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
