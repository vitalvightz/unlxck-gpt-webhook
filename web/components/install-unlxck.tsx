"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Image from "next/image";

import { usePwaRuntime } from "@/components/pwa-register";
import { rememberInstallGuideDismissal } from "@/lib/pwa";
import { useTranslations as useAppTranslations } from "next-intl";


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

export function InstallUnlxck({ variant = "panel" }: { variant?: "panel" | "inline" }) {
    const appText = useAppTranslations("AppText");
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
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || !dialog?.contains(document.activeElement))
      ) {
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

  // The sheet is fixed-position, so it must escape ancestors whose entrance
  // animations retain a transform (they become the containing block and push
  // the sheet off-screen). Portaling to <body> keeps it viewport-anchored.
  const installSheet = showGuide
    ? createPortal(
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
                <p className="pwa-install-label">{appText("text_b55128539700")}</p>
                <h2 id="pwa-install-sheet-title">{appText("text_ea6a60bcb37d")}</h2>
              </div>
              <button ref={closeRef} type="button" className="pwa-install-sheet-close" onClick={dismissGuide} aria-label={appText("text_87171467af2c")}>
                <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path d="M5 5l10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            <p id="pwa-install-sheet-description" className="muted">
              {appText("text_65f2b9b2eb92")}</p>
            <ol className="pwa-install-steps">
              <li>
                <span className="pwa-install-step-icon"><ShareIcon /></span>
                <span><strong>{appText("text_8e34d7ea4d22")}</strong><small>{appText("text_39ec9886209c")}</small></span>
              </li>
              <li>
                <span className="pwa-install-step-icon"><AddToHomeIcon /></span>
                <span><strong>{appText("text_3baaed53bac5")}</strong><small>{appText("text_d6167c105e54")}</small></span>
              </li>
              <li>
                <span className="pwa-install-step-number">{appText("text_0b8efa5a3bf1")}</span>
                <span><strong>{appText("text_154b0ca23e91")}</strong><small>{appText("text_c5079a634bd6")}</small></span>
              </li>
            </ol>
            <button type="button" className="ghost-button pwa-install-sheet-done" onClick={dismissGuide}>
              {appText("text_11a6767d5674")}</button>
          </section>
        </div>,
        document.body,
      )
    : null;

  if (variant === "inline") {
    return (
      <>
        <div className="pwa-install-inline" data-testid="install-unlxck-inline">
          <div className="pwa-install-inline-copy">
            <p className="pwa-install-label">{appText("text_f1a2806d9969")}</p>
            <p className="muted pwa-install-inline-text">
              {appText("text_8e6193a929b0")}</p>
          </div>
          <button
            ref={triggerRef}
            type="button"
            className="secondary-button pwa-install-inline-button"
            onClick={() => void handleInstall()}
          >
            {canPromptInstall ? appText("text_ea6a60bcb37d") : appText("text_494ea53ea441")}
          </button>
        </div>
        {installSheet}
      </>
    );
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
              <p className="pwa-install-label">{appText("text_f1a2806d9969")}</p>
              <h3 className="settings-subsection-title">{appText("text_ea6a60bcb37d")}</h3>
            </div>
          </div>
          <p className="muted pwa-install-description">
            {appText("text_a3df38cbbdeb")}</p>
        </div>
        <div className="pwa-install-actions">
          <button ref={triggerRef} type="button" className="cta" onClick={() => void handleInstall()}>
            {canPromptInstall ? appText("text_ea6a60bcb37d") : appText("text_494ea53ea441")}
          </button>
        </div>
      </div>

      {installSheet}
    </>
  );
}
