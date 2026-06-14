"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type TransitionEvent } from "react";

import { useAppSession } from "@/components/auth-provider";
import { Skeleton } from "@/components/skeleton";
import { shouldShowAdminPanelLink } from "@/lib/admin-nav-visibility";
import { isSafeAvatarImageUrl } from "@/lib/avatar-image-url";
import { SIDE_NAV_ITEMS } from "@/lib/beta-navigation";

type MobileNavState = "closed" | "opening" | "open" | "closing";

const MOBILE_NAV_CLOSE_MS = 240;
const MOBILE_NAV_MEDIA_QUERY = "(max-width: 960px)";
const BRAND_SURFACE_ROUTES = new Set(["/", "/login", "/signup", "/forgot-password", "/reset-password"]);

function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function getShellSurface(pathname: string, hasSession: boolean): "brand" | "workspace" {
  if (hasSession) {
    return "workspace";
  }

  return BRAND_SURFACE_ROUTES.has(pathname) ? "brand" : "workspace";
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

function MenuIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" aria-hidden="true" focusable="false">
      <path d="M4 6h12M4 10h12M4 14h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function AppNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { isReady, isMeHydrated, session, me, signOut } = useAppSession();
  const [mobileNavState, setMobileNavState] = useState<MobileNavState>("closed");
  const [desktopNavCollapsed, setDesktopNavCollapsed] = useState(false);
  const [pendingNavHref, setPendingNavHref] = useState<string | null>(null);
  const closeTimeoutRef = useRef<number | null>(null);
  const desktopNavToggleRef = useRef<HTMLButtonElement | null>(null);
  const hasSession = Boolean(session);
  const isSessionResolving = Boolean(session && !isMeHydrated);
  const shellSurface = getShellSurface(pathname, hasSession);

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

  const isMobileNavExpanding = mobileNavState === "opening" || mobileNavState === "open";

  useEffect(() => {
    if (!isMobileNavExpanding) {
      return;
    }
    document.documentElement.dataset.mobileNavOpen = "true";
    return () => {
      delete document.documentElement.dataset.mobileNavOpen;
    };
  }, [isMobileNavExpanding]);

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

  useEffect(() => {
    if (pendingNavHref && isActive(pathname, pendingNavHref)) {
      setPendingNavHref(null);
    }
  }, [pathname, pendingNavHref]);

  function handleSidebarLinkSelect(href: string) {
    setPendingNavHref(href);
    closeMobileDrawer();
  }

  function isLinkActive(href: string): boolean {
    if (pendingNavHref === href) {
      return true;
    }
    return isActive(pathname, href);
  }

  useEffect(() => {
    document.documentElement.dataset.appSurface = shellSurface;

    return () => {
      delete document.documentElement.dataset.appSurface;
    };
  }, [shellSurface]);

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

  const signedInLinks = SIDE_NAV_ITEMS;

  const profile = me?.profile;
  const displayName = profile?.full_name || "Athlete";
  const displayEmail = profile?.email || session?.email || "Session active";
  const initials = getInitials(displayName);
  const avatarUrl = profile && isSafeAvatarImageUrl(profile.avatar_url) ? profile.avatar_url : null;
  const role = profile?.role ?? null;
  const isAdminWorkspace = shouldShowAdminPanelLink(role, isActive(pathname, "/admin"));

  return (
    <>
      {shellSurface === "brand" && isReady && !session ? (
        <header className="brand-topbar" aria-label="UNLXCK entry navigation">
          <Link href="/" className="brand-topbar-mark">
            <span className="eyebrow">UNLXCK</span>
            <span>Fight Camp</span>
          </Link>
          <nav className="brand-topbar-actions" aria-label="Account access">
            <Link href="/login" className="ghost-button">
              Log in
            </Link>
            <Link href="/signup" className="cta">
              Start free beta
            </Link>
          </nav>
        </header>
      ) : null}
      {!isMobileDrawerVisible ? (
        <button
          type="button"
          className="mobile-nav-toggle"
          aria-label="Open navigation"
          aria-expanded={false}
          aria-controls="app-sidebar"
          onClick={openMobileDrawer}
        >
          <span className="nav-toggle-icon" aria-hidden="true">
            <MenuIcon />
          </span>
          <span className="nav-toggle-label">Menu</span>
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
          <span className="nav-toggle-icon" aria-hidden="true">
            <MenuIcon />
          </span>
          <span className="nav-toggle-label">Menu</span>
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
                aria-label="Close menu"
                onClick={handleSidebarClose}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            <Link href="/" className="brand" onClick={closeMobileDrawer}>
              Fight Camp
            </Link>
            <p className="sidebar-tagline">Fight-camp workspace.</p>
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
                  className={isLinkActive("/signup") ? "sidebar-link sidebar-link-active" : "sidebar-link"}
                  onClick={() => handleSidebarLinkSelect("/signup")}
                >
                  <div className="sidebar-link-copy">
                    <span className="sidebar-link-title">Create account</span>
                    <span className="sidebar-link-meta">Start athlete setup</span>
                  </div>
                </Link>
                <Link
                  href="/login"
                  className={isLinkActive("/login") ? "sidebar-link sidebar-link-active" : "sidebar-link"}
                  onClick={() => handleSidebarLinkSelect("/login")}
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
                    className={isLinkActive(link.href) ? "sidebar-link sidebar-link-active" : "sidebar-link"}
                    href={link.href}
                    onClick={() => handleSidebarLinkSelect(link.href)}
                  >
                    <div className="sidebar-link-copy">
                      <span className="sidebar-link-title">{link.label}</span>
                      <span className="sidebar-link-meta">{link.meta}</span>
                    </div>
                  </Link>
                ))}
                {isAdminWorkspace ? (
                  <>
                    <div className="sidebar-admin-divider" aria-hidden="true" />
                    <p className="sidebar-section-label">Control</p>
                    <Link
                      className={isLinkActive("/admin") ? "sidebar-link sidebar-link-active" : "sidebar-link"}
                      href="/admin"
                      onClick={() => handleSidebarLinkSelect("/admin")}
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
                      <p className="sidebar-user-email">{displayEmail}</p>
                      {role ? (
                        <span
                          className={`sidebar-role-badge sidebar-role-${role}`}
                          aria-label={`Role: ${role === "admin" ? "Administrator" : "Athlete"}`}
                        >
                          {role === "admin" ? "Admin" : "Athlete"}
                        </span>
                      ) : isSessionResolving ? (
                        <Skeleton variant="block" width={74} height={24} style={{ borderRadius: 999 }} />
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
