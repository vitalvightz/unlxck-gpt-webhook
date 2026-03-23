import type { ReactNode } from "react";
import type { Metadata } from "next";

import { AppNav } from "@/components/app-nav";
import { AppearanceProvider } from "@/components/appearance-provider";
import { AuthProvider } from "@/components/auth-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "UNLXCK Athlete Control Room",
  description: "Athlete-first fight camp planning on the web.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Space+Grotesk:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <AppearanceProvider>
          <AuthProvider>
            <div className="app-shell">
              <AppNav />
              <main className="app-main">
                <div className="page">{children}</div>
              </main>
            </div>
          </AuthProvider>
        </AppearanceProvider>
      </body>
    </html>
  );
}
