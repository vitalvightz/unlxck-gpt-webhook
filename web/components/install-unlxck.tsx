"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";

import { usePwaRuntime } from "@/components/pwa-register";
import { rememberInstallGuideDismissal } from "@/lib/pwa";

function ShareIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 15V3m0 0L8 7m4-4 4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7 10H5.8A1.8 1.8 0 0 0 4 11.8v7.4A1.8 1.8 0 0 0 5.8 21h12.4a1.8 1.8 0 0 0 1.8-1.8v-7.4a1.8 1.8 0 0 0-1.8-1.8H17" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function AddToHomeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="3.5" width="17" height="17" rx="3" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 8v8M8 12h8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function InstallUnlxck() {
  const { installAvailability, isInstalled, promptInstall } = usePwaRuntime();
  const canPromptInstall = installAvailability === "native";
  const isIos = installAvailability === "ios-manual";
  const [showGuide, setShowGuide] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!showGuide) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setShowGuide(false);
        return;
      }
      if (event.key !== "Tab") {
        return;
      }

      const dialog = dialogRef.current;
      const focusable = Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((element) => !element.hasAttribute("hidden"));
      const first = focusable[0];
      const last = focusable.at(-1);

      if (!first || !last) {
        event.preventDefault();
        return;
      }
      if (event.shiftKey && (document.activeElement === first || !dialog?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const trigger = triggerRef.current;

    document.documentElement.dataset.pwaInstallSheet = "open";
    document.body.dataset.pwaInstallSheet = "open";
    closeRef.current?.focus();
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      delete document.documentElement.dataset.pwaInstallSheet;
      delete document.body.dataset.pwaInstallSheet;
      window.removeEventListener("keydown", handleKeyDown);
      trigger?.focus();
    };
  }, [showGuide]);

  function dismissGuide() {
    rememberInstallGuideDismissal(window.localStorage);
    setShowGuide(false);
  }

  async function handleInstall() {
    if (canPromptInstall) {
      const outcome = await promptInstall();
      if (outcome === "dismissed") {
        rememberInstallGuideDismissal(window.localStorage);
      }
      return;
    }
    if (isIos) {
      setShowGuide(true);
    }
  }

  if (
    isInstalled !== false ||
    (installAvailability !== "native" && installAvailability !== "ios-manual")
  ) {
    return null;
  }

  return (
    <>
      <div className="settings-subsection pwa-install-panel" data-testid="install-unlxck">
        <div className="pwa-install-mark" aria-hidden="true">
          <Image src="/icons/icon-192x192.png" alt="" width={64} height={64} />
        </div>
        <div className="pwa-install-copy">
          <div className="settings-subsection-header">
            <div>
              <p className="pwa-install-label">Mobile access</p>
              <h3 className="settings-subsection-title">Install UNLXCK</h3>
            </div>
          </div>
          <p className="muted pwa-install-description">
            Open your control room from a home-screen icon in a focused, standalone window.
          </p>
        </div>
        <div className="pwa-install-actions">
          <button ref={triggerRef} type="button" className="cta" onClick={() => void handleInstall()}>
            {canPromptInstall ? "Install UNLXCK" : "View iPhone steps"}
          </button>
        </div>
      </div>

      {showGuide ? (
        <div
          className="pwa-install-sheet-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              dismissGuide();
            }
          }}
        >
          <section
            ref={dialogRef}
            className="pwa-install-sheet"
            role="dialog"
            aria-modal="true"
            aria-labelledby="pwa-install-sheet-title"
            aria-describedby="pwa-install-sheet-description"
          >
            <div className="pwa-install-sheet-header">
              <div>
                <p className="pwa-install-label">Add to your device</p>
                <h2 id="pwa-install-sheet-title">Install UNLXCK</h2>
              </div>
              <button ref={closeRef} type="button" className="pwa-install-sheet-close" onClick={dismissGuide} aria-label="Close install instructions">
                <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path d="M5 5l10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            <p id="pwa-install-sheet-description" className="muted">
              Safari uses the Share menu to add a web app to your Home Screen.
            </p>
            <ol className="pwa-install-steps">
              <li>
                <span className="pwa-install-step-icon"><ShareIcon /></span>
                <span><strong>Open the Share menu</strong><small>Tap the Share icon in Safari’s toolbar.</small></span>
              </li>
              <li>
                <span className="pwa-install-step-icon"><AddToHomeIcon /></span>
                <span><strong>Select “Add to Home Screen”</strong><small>Scroll the actions list if it is not immediately visible.</small></span>
              </li>
              <li>
                <span className="pwa-install-step-number">03</span>
                <span><strong>Tap “Add”</strong><small>UNLXCK will appear with its own icon and launch standalone.</small></span>
              </li>
            </ol>
            <button type="button" className="ghost-button pwa-install-sheet-done" onClick={dismissGuide}>
              Done
            </button>
          </section>
        </div>
      ) : null}
    </>
  );
}
