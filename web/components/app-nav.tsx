"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAppSession } from "@/components/auth-provider";

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function getInitials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
}

export function AppNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { isReady, session, me, signOut } = useAppSession();
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    setIsOpen(false);
  }, [pathname, session]);

  async function handleSignOut() {
    await signOut();
    router.push("/");
  }

  const signedInLinks = [
    { href: "/", label: "Overview", meta: "Camp status" },
    { href: "/onboarding", label: "Onboarding", meta: "Profile and intake" },
    { href: "/plans", label: "Plans", meta: "Saved history" },
    { href: "/settings", label: "Settings", meta: "Athlete profile" },
  ];

  const profile = me?.profile;
  const displayName = profile?.full_name || "Athlete";
  const initials = getInitials(displayName);
  const avatarUrl = profile?.avatar_url || null;
  const role = profile?.role ?? null;

  return (
    <>
      <button
        type="button"
        className="mobile-nav-toggle"
        aria-label={isOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={isOpen}
        aria-controls="app-sidebar"
        onClick={() => setIsOpen((current) => !current)}
      >
        <span>{isOpen ? "Close" : "Menu"}</span>
        {!session && isReady ? <span className="badge status-badge-neutral">Entry</span> : null}
      </button>
      {isOpen ? (
        <button type="button" className="nav-scrim" aria-label="Close navigation" onClick={() => setIsOpen(false)} />
      ) : null}
      <aside id="app-sidebar" className={`app-sidebar ${isOpen ? "app-sidebar-open" : ""}`}>
        <div className="sidebar-shell">
          <div className="sidebar-brand">
            <p className="eyebrow">UNLXCK</p>
            <Link href="/" className="brand">
              Fight Camp
            </Link>
            <p className="sidebar-tagline">Athlete fight-camp workspace.</p>
            <span className="sidebar-beta">Beta</span>
          </div>

          {!isReady ? (
            <div className="sidebar-nav">
              <p className="sidebar-section-label">Loading</p>
              <div className="sidebar-user-card">
                <p className="sidebar-user-name">Checking session</p>
                <p className="sidebar-user-email">Loading your workspace.</p>
              </div>
            </div>
          ) : null}

          {isReady && !session ? (
            <>
              <div className="sidebar-auth">
                <p className="sidebar-section-label">Entry</p>
                <Link href="/signup" className={isActive(pathname, "/signup") ? "sidebar-link sidebar-link-active" : "sidebar-link"}>
                  <div className="sidebar-link-copy">
                    <span className="sidebar-link-title">Create account</span>
                    <span className="sidebar-link-meta">Start athlete setup</span>
                  </div>
                </Link>
                <Link href="/login" className={isActive(pathname, "/login") ? "sidebar-link sidebar-link-active" : "sidebar-link"}>
                  <div className="sidebar-link-copy">
                    <span className="sidebar-link-title">Log in</span>
                    <span className="sidebar-link-meta">Resume onboarding or plans</span>
                  </div>
                </Link>
              </div>
              <div className="sidebar-user-card">
                <p className="sidebar-section-label">Signed out</p>
                <p className="sidebar-user-name">Athlete-first entry</p>
                <p className="sidebar-user-email">Build, generate, and reopen plans in one place.</p>
              </div>
            </>
          ) : null}

          {isReady && session ? (
            <>
              <nav className="sidebar-nav">
                <p className="sidebar-section-label">Athlete</p>
                {signedInLinks.map((link) => (
                  <Link
                    key={link.href}
                    className={isActive(pathname, link.href) ? "sidebar-link sidebar-link-active" : "sidebar-link"}
                    href={link.href}
                  >
                    <div className="sidebar-link-copy">
                      <span className="sidebar-link-title">{link.label}</span>
                      <span className="sidebar-link-meta">{link.meta}</span>
                    </div>
                  </Link>
                ))}
                {profile?.role === "admin" ? (
                  <>
                    <div className="sidebar-admin-divider" aria-hidden="true" />
                    <p className="sidebar-section-label">Admin</p>
                    <Link
                      className={isActive(pathname, "/admin") ? "sidebar-link sidebar-link-active" : "sidebar-link"}
                      href="/admin"
                    >
                      <div className="sidebar-link-copy">
                        <span className="sidebar-link-title">Admin panel</span>
                        <span className="sidebar-link-meta">Review and support</span>
                      </div>
                    </Link>
                  </>
                ) : null}
              </nav>
              <div className="sidebar-footer">
                <p className="sidebar-section-label">Signed in</p>
                <div className="sidebar-user-card">
                  <div className="sidebar-user-identity">
                    <div className="sidebar-avatar" aria-hidden="true">
                      {avatarUrl ? (
                        <img src={avatarUrl} alt="" className="sidebar-avatar-img" />
                      ) : (
                        <span className="sidebar-avatar-initials">{initials}</span>
                      )}
                    </div>
                    <div className="sidebar-user-info">
                      <p className="sidebar-user-name">{displayName}</p>
                      <p className="sidebar-user-email">{profile?.email}</p>
                      {role ? (
                        <span
                          className={`sidebar-role-badge sidebar-role-${role}`}
                          aria-label={`Role: ${role === "admin" ? "Administrator" : "Athlete"}`}
                        >
                          {role}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="sidebar-user-actions">
                    <button type="button" className="ghost-button" onClick={handleSignOut}>
                      Log out
                    </button>
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </aside>
    </>
  );
}
