"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useToast } from "@/components/toast-provider";
import {
  createPwaWorkerUrl,
  isIosDevice,
  isPwaCriticalWorkflow,
  isStandaloneDisplay,
  PWA_DISPLAY_MODE_QUERY,
  resolvePwaInstallAvailability,
  shouldReloadForPwaControllerChange,
  shouldRegisterServiceWorker,
  type PwaInstallAvailability,
} from "@/lib/pwa";

type InstallOutcome = "accepted" | "dismissed" | "unavailable";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

interface NavigatorWithStandalone extends Navigator {
  standalone?: boolean;
}

interface PwaRuntimeContextValue {
  installAvailability: PwaInstallAvailability;
  isInstalled: boolean | null;
  promptInstall: () => Promise<InstallOutcome>;
}

const PwaRuntimeContext = createContext<PwaRuntimeContextValue>({
  installAvailability: "checking",
  isInstalled: null,
  promptInstall: async () => "unavailable",
});

const UPDATE_SAFETY_POLL_MS = 1_000;
const reloadCurrentPage = () => window.location.reload();

export function usePwaRuntime(): PwaRuntimeContextValue {
  return useContext(PwaRuntimeContext);
}

export function PwaRegister({
  children,
  buildVersion = "local",
  environment = process.env.NODE_ENV,
  reloadPage = reloadCurrentPage,
}: Readonly<{
  children: ReactNode;
  buildVersion?: string;
  environment?: string;
  reloadPage?: () => void;
}>) {
  const { dismissToast, showToast } = useToast();
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isInstalled, setIsInstalled] = useState<boolean | null>(null);
  const [isIos, setIsIos] = useState(false);
  const [waitingUpdateVersion, setWaitingUpdateVersion] = useState(0);
  const [isUpdateContextCritical, setIsUpdateContextCritical] = useState(false);
  const waitingWorkerRef = useRef<ServiceWorker | null>(null);
  const updateToastIdRef = useRef<number | null>(null);
  const unsavedInputRef = useRef(false);
  const lastRouteKeyRef = useRef("");
  const updateContextCriticalRef = useRef<boolean | null>(null);
  const refreshRequestedRef = useRef(false);
  const reloadStartedRef = useRef(false);

  const activateWaitingWorker = useCallback(() => {
    const worker = waitingWorkerRef.current;
    if (!worker) {
      return;
    }
    updateToastIdRef.current = null;
    refreshRequestedRef.current = true;
    worker.postMessage({ type: "SKIP_WAITING" });
  }, []);

  const storeWaitingWorker = useCallback(
    (worker: ServiceWorker | null) => {
      if (!worker || waitingWorkerRef.current === worker) {
        return;
      }
      if (updateToastIdRef.current !== null) {
        dismissToast(updateToastIdRef.current);
        updateToastIdRef.current = null;
      }
      waitingWorkerRef.current = worker;
      setWaitingUpdateVersion((current) => current + 1);
    },
    [dismissToast],
  );

  const evaluateUpdateSafety = useCallback(() => {
    const routeKey = `${window.location.pathname}${window.location.search}`;
    if (lastRouteKeyRef.current && lastRouteKeyRef.current !== routeKey) {
      unsavedInputRef.current = false;
    }
    lastRouteKeyRef.current = routeKey;

    const nextCritical =
      unsavedInputRef.current ||
      isPwaCriticalWorkflow(window.location.pathname, window.location.search);
    if (updateContextCriticalRef.current === nextCritical) {
      return;
    }
    updateContextCriticalRef.current = nextCritical;
    setIsUpdateContextCritical(nextCritical);
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia?.(PWA_DISPLAY_MODE_QUERY);
    const navigatorWithStandalone = navigator as NavigatorWithStandalone;

    const syncInstalledState = () => {
      setIsInstalled(
        isStandaloneDisplay(mediaQuery?.matches ?? false, navigatorWithStandalone.standalone),
      );
    };
    const handleBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    };
    const handleAppInstalled = () => {
      setInstallPrompt(null);
      setIsInstalled(true);
    };

    const frameId = window.requestAnimationFrame(() => {
      setIsIos(isIosDevice(navigator.userAgent, navigator.maxTouchPoints));
      syncInstalledState();
    });
    mediaQuery?.addEventListener?.("change", syncInstalledState);
    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
    window.addEventListener("appinstalled", handleAppInstalled);

    return () => {
      window.cancelAnimationFrame(frameId);
      mediaQuery?.removeEventListener?.("change", syncInstalledState);
      window.removeEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
      window.removeEventListener("appinstalled", handleAppInstalled);
    };
  }, []);

  useEffect(() => {
    const isEditableTarget = (target: EventTarget | null) => {
      if (!(target instanceof HTMLElement)) {
        return false;
      }
      if (target.isContentEditable) {
        return true;
      }
      if (
        target instanceof window.HTMLTextAreaElement ||
        target instanceof window.HTMLSelectElement
      ) {
        return !target.hasAttribute("disabled");
      }
      if (!(target instanceof window.HTMLInputElement)) {
        return false;
      }
      return (
        !target.disabled &&
        !target.readOnly &&
        !["button", "hidden", "reset", "submit"].includes(target.type)
      );
    };
    const markUnsavedInput = (event: Event) => {
      if (!isEditableTarget(event.target) || unsavedInputRef.current) {
        return;
      }
      unsavedInputRef.current = true;
      evaluateUpdateSafety();
    };
    const clearUnsavedInput = () => {
      if (!unsavedInputRef.current) {
        return;
      }
      unsavedInputRef.current = false;
      window.requestAnimationFrame(evaluateUpdateSafety);
    };

    document.addEventListener("input", markUnsavedInput, true);
    document.addEventListener("change", markUnsavedInput, true);
    document.addEventListener("submit", clearUnsavedInput, true);
    document.addEventListener("reset", clearUnsavedInput, true);

    return () => {
      document.removeEventListener("input", markUnsavedInput, true);
      document.removeEventListener("change", markUnsavedInput, true);
      document.removeEventListener("submit", clearUnsavedInput, true);
      document.removeEventListener("reset", clearUnsavedInput, true);
    };
  }, [evaluateUpdateSafety]);

  useEffect(() => {
    evaluateUpdateSafety();
    if (waitingUpdateVersion === 0) {
      return;
    }

    const intervalId = window.setInterval(evaluateUpdateSafety, UPDATE_SAFETY_POLL_MS);
    window.addEventListener("focus", evaluateUpdateSafety);
    window.addEventListener("popstate", evaluateUpdateSafety);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", evaluateUpdateSafety);
      window.removeEventListener("popstate", evaluateUpdateSafety);
    };
  }, [evaluateUpdateSafety, waitingUpdateVersion]);

  useEffect(() => {
    if (waitingUpdateVersion === 0) {
      return;
    }

    const isCritical =
      isUpdateContextCritical ||
      unsavedInputRef.current ||
      isPwaCriticalWorkflow(window.location.pathname, window.location.search);

    if (isCritical) {
      if (updateToastIdRef.current !== null) {
        dismissToast(updateToastIdRef.current);
        updateToastIdRef.current = null;
      }
      return;
    }
    if (updateToastIdRef.current !== null) {
      return;
    }

    updateToastIdRef.current = showToast("New version available", {
      action: { label: "Refresh", onClick: activateWaitingWorker },
      durationMs: 0,
      tone: "info",
    });
  }, [
    activateWaitingWorker,
    dismissToast,
    isUpdateContextCritical,
    showToast,
    waitingUpdateVersion,
  ]);

  useEffect(() => {
    if (!shouldRegisterServiceWorker(environment, "serviceWorker" in navigator)) {
      return;
    }

    let disposed = false;
    let registration: ServiceWorkerRegistration | null = null;
    let installingWorker: ServiceWorker | null = null;

    const handleControllerChange = () => {
      if (
        !shouldReloadForPwaControllerChange(
          refreshRequestedRef.current,
          reloadStartedRef.current,
        )
      ) {
        return;
      }
      reloadStartedRef.current = true;
      reloadPage();
    };

    const handleInstallingStateChange = () => {
      if (
        installingWorker?.state === "installed" &&
        navigator.serviceWorker.controller
      ) {
        storeWaitingWorker(registration?.waiting ?? installingWorker);
      }
    };

    const handleUpdateFound = () => {
      installingWorker?.removeEventListener("statechange", handleInstallingStateChange);
      installingWorker = registration?.installing ?? null;
      installingWorker?.addEventListener("statechange", handleInstallingStateChange);
    };

    navigator.serviceWorker.addEventListener("controllerchange", handleControllerChange);

    const workerUrl = createPwaWorkerUrl(buildVersion);

    void navigator.serviceWorker
      .register(workerUrl, { scope: "/", updateViaCache: "none" })
      .then((nextRegistration) => {
        if (disposed) {
          return;
        }
        registration = nextRegistration;
        registration.addEventListener("updatefound", handleUpdateFound);
        storeWaitingWorker(registration.waiting);
        if (registration.installing) {
          handleUpdateFound();
        }
      })
      .catch(() => {
        // PWA support is progressive enhancement; registration failures must
        // never block auth, navigation, intake, or plan generation.
      });

    return () => {
      disposed = true;
      navigator.serviceWorker.removeEventListener("controllerchange", handleControllerChange);
      registration?.removeEventListener("updatefound", handleUpdateFound);
      installingWorker?.removeEventListener("statechange", handleInstallingStateChange);
    };
  }, [buildVersion, environment, reloadPage, storeWaitingWorker]);

  const promptInstall = useCallback(async (): Promise<InstallOutcome> => {
    const prompt = installPrompt;
    if (!prompt) {
      return "unavailable";
    }

    try {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      setInstallPrompt(null);
      return choice.outcome;
    } catch {
      setInstallPrompt(null);
      return "unavailable";
    }
  }, [installPrompt]);

  const installAvailability = useMemo(
    () =>
      resolvePwaInstallAvailability({
        hasNativePrompt: installPrompt !== null,
        installed: isInstalled,
        ios: isIos,
      }),
    [installPrompt, isInstalled, isIos],
  );

  const value = useMemo<PwaRuntimeContextValue>(
    () => ({
      installAvailability,
      isInstalled,
      promptInstall,
    }),
    [installAvailability, isInstalled, promptInstall],
  );

  return <PwaRuntimeContext.Provider value={value}>{children}</PwaRuntimeContext.Provider>;
}
