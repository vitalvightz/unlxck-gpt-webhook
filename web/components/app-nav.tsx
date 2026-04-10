"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAppSession } from "@/components/auth-provider";

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function getInitials(name: string): string {
  const result = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
  return result || "A";
}

const SAFE_DATA_IMAGE_RE = /^data:image\/[a-zA-Z0-9.+\-]+;base64,[A-Za-z0-9+/]+=*$/;

function isSafeImageUrl(url: string): boolean {
  if (url.startsWith("data:image/")) {
    return SAFE_DATA_IMAGE_RE.test(url);
  }
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

export function AppNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { isReady, session, me, signOut } = useAppSession();
  const [isOpen, setIsOpen] = useState(false);

  function handleCloseNav() {
    setIsOpen(false);
  }

  function handleToggleNav() {
    setIsOpen((current) => !current);
  }

  useEffect(() => {
    setIsOpen(false);
  }, [pathname, session]);

  useEffect(() => {
    document.body.classList.toggle("app-mobile-nav-open", isOpen);
    return () => {
      document.body.classList.remove("app-mobile-nav-open");
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  async function handleSignOut() {
    handleCloseNav();
    await signOut();
    router.push("/");
  }

  const signedInLinks = [
    { href: "/", label: "Overview", meta: "Camp status" },
    { href: "/onboarding", label: "Onboarding", meta: "Profile and intake" },
    { href: "/nutrition", label: "Nutrition", meta: "Weight and readiness" },
    { href: "/plans", label: "Plans", meta: "Saved history" },
    { href: "/settings", label: "Settings", meta: "Athlete profile" },
  ];

  const profile = me?.profile;
  const displayName = profile?.full_name || "Athlete";
  const initials = getInitials(displayName);
  const avatarUrl = (profile?.avatar_url && isSafeImageUrl(profile.avatar_url)) ? profile.avatar_url : null;
  const role = profile?.role ?? null;

  return (
    <>
      <button
        type="button"
        className="mobile-nav-toggle"
        aria-label={isOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={isOpen}
        aria-controls="app-sidebar"
        onClick={handleToggleNav}
      >
        <span>{isOpen ? "Close" : "Menu"}</span>
        {!session && isReady ? <span className="badge status-badge-neutral">Entry</span> : null}
      </button>
      <button
        type="button"
        className="nav-scrim"
        data-state={isOpen ? "open" : "closed"}
        aria-label="Close navigation"
        aria-hidden={!isOpen}
        tabIndex={-1}
        onClick={handleCloseNav}
      />
      <aside
        id="app-sidebar"
        className={`app-sidebar ${isOpen ? "app-sidebar-open" : ""}`}
        data-state={isOpen ? "open" : "closed"}
      >
        <div className="sidebar-shell">
          <div className="sidebar-brand">
            <div className="sidebar-brand-topline">
              <p className="eyebrow">UNLXCK</p>
              <button type="button" className="sidebar-close-button" onClick={handleCloseNav} aria-label="Close navigation">
                Close
              </button>
            </div>
            <Link href="/" className="brand">
              Fight Camp
            </Link>
            <p className="sidebar-tagline">Athlete control room.</p>
          </div>

          {!isReady ? (
            <div className="sidebar-nav">
              <p className="sidebar-section-label">Session</p>
              <div className="sidebar-user-card">
                <p className="sidebar-user-name">Loading workspace</p>
                <p className="sidebar-user-email">Checking your session.</p>
              </div>
            </div>
          ) : null}

          {isReady && !session ? (
            <>
              <div className="sidebar-auth">
                <p className="sidebar-section-label">Access</p>
                <Link href="/signup" className={isActive(pathname, "/signup") ? "sidebar-link sidebar-link-active" : "sidebar-link"}>
                  <div className="sidebar-link-copy">
                    <span className="sidebar-link-title">Create account</span>
                    <span className="sidebar-link-meta">Start athlete setup</span>
                  </div>
                </Link>
                <Link href="/login" className={isActive(pathname, "/login") ? "sidebar-link sidebar-link-active" : "sidebar-link"}>
                  <div className="sidebar-link-copy">
                    <span className="sidebar-link-title">Log in</span>
                    <span className="sidebar-link-meta">Resume your camp</span>
                  </div>
                </Link>
              </div>
              <div className="sidebar-user-card">
                <p className="sidebar-user-name">Elite athlete entry</p>
                <p className="sidebar-user-email">Build, generate, and manage fight camps in one place.</p>
              </div>
            </>
          ) : null}

          {isReady && session ? (
            <>
              <nav className="sidebar-nav">
                <p className="sidebar-section-label">Workspace</p>
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
                    <p className="sidebar-section-label">Control</p>
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
                          {role === "admin" ? "Admin" : "Athlete"}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="sidebar-user-actions">
                    <button type="button" className="ghost-button" onClick={handleSignOut}>
                      Sign out
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
