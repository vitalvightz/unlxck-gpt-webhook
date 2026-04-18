"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type TransitionEvent } from "react";

import { useAppSession } from "@/components/auth-provider";

type MobileNavState = "closed" | "opening" | "open" | "closing";

const MOBILE_NAV_CLOSE_MS = 240;
const MOBILE_NAV_MEDIA_QUERY = "(max-width: 960px)";

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
  const [mobileNavState, setMobileNavState] = useState<MobileNavState>("closed");
  const [desktopNavCollapsed, setDesktopNavCollapsed] = useState(false);
  const closeTimeoutRef = useRef<number | null>(null);
  const desktopNavToggleRef = useRef<HTMLButtonElement | null>(null);

  const isMobileDrawerVisible = mobileNavState !== "closed";

  function clearCloseTimeout() {
    if (closeTimeoutRef.current === null) {
      return;
    }
    window.clearTimeout(closeTimeoutRef.current);
    closeTimeoutRef.current = null;
  }

  function openMobileDrawer() {
    clearCloseTimeout();
    setMobileNavState((current) => (current === "open" || current === "opening" ? current : "opening"));
  }

  function closeMobileDrawer() {
    clearCloseTimeout();
    setMobileNavState((current) => (current === "closed" || current === "closing" ? current : "closing"));
  }

  function handleSidebarClose() {
    if (window.matchMedia(MOBILE_NAV_MEDIA_QUERY).matches) {
      closeMobileDrawer();
      return;
    }

    setDesktopNavCollapsed(true);
  }

  useEffect(() => {
    if (mobileNavState !== "opening") {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      setMobileNavState((current) => (current === "opening" ? "open" : current));
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [mobileNavState]);

  useEffect(() => {
    if (mobileNavState !== "closing") {
      return;
    }

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    closeTimeoutRef.current = window.setTimeout(() => {
      setMobileNavState((current) => (current === "closing" ? "closed" : current));
      closeTimeoutRef.current = null;
    }, reducedMotion ? 0 : MOBILE_NAV_CLOSE_MS);

    return () => {
      clearCloseTimeout();
    };
  }, [mobileNavState]);

  useEffect(() => {
    return () => {
      clearCloseTimeout();
    };
  }, []);

  useEffect(() => {
    const { documentElement } = document;

    if (desktopNavCollapsed) {
      documentElement.dataset.desktopNavCollapsed = "true";
      desktopNavToggleRef.current?.focus();
      return () => {
        delete documentElement.dataset.desktopNavCollapsed;
      };
    }

    delete documentElement.dataset.desktopNavCollapsed;
    return () => {
      delete documentElement.dataset.desktopNavCollapsed;
    };
  }, [desktopNavCollapsed]);

  useEffect(() => {
    if (!isMobileDrawerVisible) {
      return;
    }

    const mediaQuery = window.matchMedia(MOBILE_NAV_MEDIA_QUERY);
    const syncScrollLock = () => {
      const shouldLock = mediaQuery.matches && isMobileDrawerVisible;
      if (shouldLock) {
        document.documentElement.dataset.mobileNavLock = "true";
        document.body.dataset.mobileNavLock = "true";
        return;
      }

      delete document.documentElement.dataset.mobileNavLock;
      delete document.body.dataset.mobileNavLock;
    };

    syncScrollLock();
    mediaQuery.addEventListener("change", syncScrollLock);

    return () => {
      mediaQuery.removeEventListener("change", syncScrollLock);
      delete document.documentElement.dataset.mobileNavLock;
      delete document.body.dataset.mobileNavLock;
    };
  }, [isMobileDrawerVisible]);

  useEffect(() => {
    if (!isMobileDrawerVisible) {
      return;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeMobileDrawer();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMobileDrawerVisible]);

  useEffect(() => {
    if (!isMobileDrawerVisible) {
      return;
    }

    closeMobileDrawer();
  }, [pathname, session]);

  async function handleSignOut() {
    closeMobileDrawer();
    await signOut();
    router.push("/");
  }

  function handleSidebarTransitionEnd(event: TransitionEvent<HTMLElement>) {
    if (event.target !== event.currentTarget || mobileNavState !== "closing") {
      return;
    }

    clearCloseTimeout();
    setMobileNavState("closed");
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
      {!isMobileDrawerVisible ? (
        <button
          type="button"
          className="mobile-nav-toggle"
          aria-label="Open navigation"
          aria-expanded={false}
          aria-controls="app-sidebar"
          onClick={openMobileDrawer}
        >
          <span>Menu</span>
          {!session && isReady ? <span className="badge status-badge-neutral">Entry</span> : null}
        </button>
      ) : null}
      {desktopNavCollapsed ? (
        <button
          ref={desktopNavToggleRef}
          type="button"
          className="desktop-nav-toggle"
          aria-label="Open navigation"
          aria-expanded={false}
          aria-controls="app-sidebar"
          onClick={() => setDesktopNavCollapsed(false)}
        >
          <span>Menu</span>
        </button>
      ) : null}
      {isMobileDrawerVisible ? (
        <button
          type="button"
          className="nav-scrim"
          data-mobile-nav-state={mobileNavState}
          aria-label="Close navigation"
          onClick={closeMobileDrawer}
        />
      ) : null}
      <aside
        id="app-sidebar"
        className="app-sidebar"
        data-mobile-nav-state={mobileNavState}
        data-mobile-nav-visible={isMobileDrawerVisible}
        onTransitionEnd={handleSidebarTransitionEnd}
      >
        <div className="sidebar-shell">
          <div className="sidebar-brand">
            <div className="sidebar-brand-header">
              <p className="eyebrow">UNLXCK</p>
              <button
                type="button"
                className="sidebar-drawer-close"
                aria-label="Close navigation"
                onClick={handleSidebarClose}
              >
                Close
              </button>
            </div>
            <Link href="/" className="brand" onClick={closeMobileDrawer}>
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
                <Link
                  href="/signup"
                  className={isActive(pathname, "/signup") ? "sidebar-link sidebar-link-active" : "sidebar-link"}
                  onClick={closeMobileDrawer}
                >
                  <div className="sidebar-link-copy">
                    <span className="sidebar-link-title">Create account</span>
                    <span className="sidebar-link-meta">Start athlete setup</span>
                  </div>
                </Link>
                <Link
                  href="/login"
                  className={isActive(pathname, "/login") ? "sidebar-link sidebar-link-active" : "sidebar-link"}
                  onClick={closeMobileDrawer}
                >
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
                    onClick={closeMobileDrawer}
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
                      onClick={closeMobileDrawer}
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
