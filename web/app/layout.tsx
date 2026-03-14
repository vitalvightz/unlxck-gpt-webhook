import type { ReactNode } from "react";
import type { Metadata } from "next";
import { IBM_Plex_Mono, Space_Grotesk } from "next/font/google";

import { AppNav } from "@/components/app-nav";
import { AuthProvider } from "@/components/auth-provider";
import "./globals.css";

const display = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "UNLXCK Athlete Control Room",
  description: "Athlete-first fight camp planning on the web.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${mono.variable}`}>
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