import type { ReactNode } from "react";
import type { Metadata } from "next";

import { AppNav } from "@/components/app-nav";
import { AuthProvider } from "@/components/auth-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "UNLXCK Athlete Control Room",
  description: "Athlete-first fight camp planning on the web.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <div className="app-shell">
            <AppNav />
            <main className="app-main">
              <div className="page">{children}</div>
            </main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
