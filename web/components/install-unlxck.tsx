"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import Image from "next/image";

import { usePwaRuntime } from "@/components/pwa-register";
import {
  hasSeenInstallPrompt,
  rememberInstallGuideDismissal,
  rememberInstallPromptSeen,
  resolveIosInstallBrowser,
  type IosInstallBrowser,
} from "@/lib/pwa";
import { lockOverlayScroll } from "@/lib/overlay-scroll-lock";
import { INSTALL_PROMPT_EVENT } from "@/lib/push-prompt";
import promptStyles from "./push-notification-prompt.module.css";
import styles from "./install-unlxck.module.css";

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

function MoreIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="5.5" cy="12" r="1.7" /><circle cx="12" cy="12" r="1.7" /><circle cx="18.5" cy="12" r="1.7" />
    </svg>
  );
}

function AddIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m5 12.5 4.5 4.5L19 7.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

type IosGuide = Exclude<IosInstallBrowser, "unsupported">;
type InstallStep = { icon: ReactNode; title: string; hint: string };

const FIND_ADD_TO_HOME: InstallStep = {
  icon: <AddToHomeIcon />, title: "Tap Add to Home Screen", hint: "Can’t find it? Scroll down or tap View More.",
};

const IOS_STEPS: Record<IosGuide, InstallStep[]> = {
  safari: [
    { icon: <MoreIcon />, title: "Tap ••• in Safari’s toolbar", hint: "Share icon showing? Tap it and skip to step 3." },
    { icon: <ShareIcon />, title: "Select Share", hint: "It opens the share sheet." },
    { icon: <AddToHomeIcon />, title: "Tap Add to Home Screen", hint: "Can’t find it? Tap View More." },
    { icon: <AddIcon />, title: "Tap Add", hint: "Keep Open as Web App switched on." },
  ],
  "safari-legacy": [
    { icon: <ShareIcon />, title: "Tap the Share icon", hint: "It sits in Safari’s toolbar." },
    { icon: <AddToHomeIcon />, title: "Tap Add to Home Screen", hint: "Scroll down the list if you can’t see it." },
    { icon: <AddIcon />, title: "Tap Add", hint: "Top right of the screen." },
  ],
  chrome: [
    { icon: <ShareIcon />, title: "Tap the Share icon", hint: "In Chrome’s address bar, or under ••• then Share." },
    FIND_ADD_TO_HOME,
    { icon: <AddIcon />, title: "Tap Add", hint: "If Open as Web App appears, keep it on." },
  ],
  other: [
    { icon: <MoreIcon />, title: "Open your browser menu", hint: "Then tap Share." },
    FIND_ADD_TO_HOME,
    { icon: <AddIcon />, title: "Tap Add", hint: "If Open as Web App appears, keep it on." },
  ],
};

/** One-time automatic offer after a saved session. Takes priority over the
 * notification prompt for that moment and reuses the PWA runtime's install
 * detection; Settings keeps the manual route. */
export function InstallPrompt() {
  const { installAvailability, promptInstall } = usePwaRuntime();
  const dialog = useRef<HTMLDialogElement>(null);
  const availability = useRef(installAvailability);
  const [guide, setGuide] = useState<"native" | IosGuide | null>(null);
  const [busy, setBusy] = useState(false);
  // A guide only stays up while the browser still offers that route.
  const shown = guide === "native" ? installAvailability === "native" : guide !== null && installAvailability === "ios-manual";

  useEffect(() => {
    availability.current = installAvailability;
  }, [installAvailability]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    const resolveGuide = () => {
      if (availability.current === "native") return "native";
      if (availability.current !== "ios-manual") return null;
      const browser = resolveIosInstallBrowser(navigator.userAgent);
      return browser === "unsupported" ? null : browser;
    };
    function onOffer(event: Event) {
      if (timer || !resolveGuide() || hasSeenInstallPrompt(window.localStorage)) return;
      event.preventDefault();
      // Let completion review, sparring safety reports and other modals finish.
      timer = setInterval(() => {
        if (document.visibilityState !== "visible" || document.querySelector('dialog[open], [aria-modal="true"]')) return;
        clearInterval(timer);
        setGuide(resolveGuide());
      }, 500);
    }
    window.addEventListener(INSTALL_PROMPT_EVENT, onOffer);
    return () => {
      clearInterval(timer);
      window.removeEventListener(INSTALL_PROMPT_EVENT, onOffer);
    };
  }, []);

  useEffect(() => {
    if (!shown || !dialog.current) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const node = dialog.current;
    const release = lockOverlayScroll();
    try {
      node.showModal();
    } catch {
      release();
      return;
    }
    if (node.open) rememberInstallPromptSeen(window.localStorage);
    return () => {
      node.close();
      release();
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, [shown]);

  async function install() {
    setBusy(true);
    try {
      // The browser reports the result; appinstalled is the only proof of install.
      await promptInstall();
    } finally {
      setBusy(false);
      setGuide(null);
    }
  }

  if (!shown) return null;
  return (
    <dialog ref={dialog} className={`${promptStyles.dialog} ${styles.dialog}`} aria-labelledby="install-prompt-title" aria-describedby="install-prompt-description" aria-busy={busy}
      onCancel={(event) => { event.preventDefault(); if (!busy) setGuide(null); }}>
      <div className={`${promptStyles.header} ${styles.header}`}>
        <Image src="/brand/unlxck-one-angle-48.png" alt="" width={28} height={28} className={promptStyles.mark} />
        <p className={promptStyles.eyebrow}>GET UNLXCK ON YOUR PHONE</p>
      </div>
      <h2 id="install-prompt-title"><span className={styles.headline}>Your training. One tap away.</span></h2>
      <p id="install-prompt-description" className={`${promptStyles.description} ${styles.description}`}>
        Add UNLXCK to your Home Screen for quick access, just like an app.
      </p>
      {guide === "native" ? (
        <button type="button" className={promptStyles.enable} onClick={() => void install()} disabled={busy}>
          {busy ? "Waiting for your browser…" : "Install UNLXCK"}<AddToHomeIcon />
        </button>
      ) : (
        <>
          <ol className={styles.steps} aria-label="Add UNLXCK to your Home Screen">
            {IOS_STEPS[guide!].map((step) => (
              <li key={step.title}>
                <span className={styles.stepIcon}>{step.icon}</span>
                <span><strong>{step.title}</strong><small>{step.hint}</small></span>
              </li>
            ))}
          </ol>
          <p className={styles.done}>That’s it. UNLXCK will be on your Home Screen.</p>
          <button type="button" className={promptStyles.enable} onClick={() => setGuide(null)}>
            Got it<AddIcon />
          </button>
        </>
      )}
      <button type="button" className={promptStyles.later} disabled={busy} onClick={() => setGuide(null)}>Maybe later</button>
    </dialog>
  );
}

export function InstallUnlxck({ variant = "panel" }: { variant?: "panel" | "inline" }) {
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

    const releaseScroll = lockOverlayScroll();
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
    closeRef.current?.focus({ preventScroll: true });
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      delete document.documentElement.dataset.pwaInstallSheet;
      delete document.body.dataset.pwaInstallSheet;
      window.removeEventListener("keydown", handleKeyDown);
      releaseScroll();
      trigger?.focus({ preventScroll: true });
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
        </div>,
        document.body,
      )
    : null;

  if (variant === "inline") {
    return (
      <>
        <div className="pwa-install-inline" data-testid="install-unlxck-inline">
          <div className="pwa-install-inline-copy">
            <p className="pwa-install-label">Mobile access</p>
            <p className="muted pwa-install-inline-text">
              Add UNLXCK to your phone’s home screen and open it like an app.
            </p>
          </div>
          <button
            ref={triggerRef}
            type="button"
            className="secondary-button pwa-install-inline-button"
            onClick={() => void handleInstall()}
          >
            {canPromptInstall ? "Install UNLXCK" : "View iPhone steps"}
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

      {installSheet}
    </>
  );
}
