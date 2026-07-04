import type { ReactNode } from "react";
import type { Metadata } from "next";
import type { Viewport } from "next";

import { AppNav } from "@/components/app-nav";
import { AuthProvider } from "@/components/auth-provider";
import { GenerationStatusShell } from "@/components/generation-status-shell";
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
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" data-theme="dark" style={{ colorScheme: "dark" }} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
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
          </ToastProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
