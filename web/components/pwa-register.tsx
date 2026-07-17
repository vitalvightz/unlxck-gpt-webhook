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
  isStandaloneDisplay,
  PWA_DISPLAY_MODE_QUERY,
  shouldRegisterServiceWorker,
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
  canPromptInstall: boolean;
  isInstalled: boolean | null;
  isIos: boolean;
  promptInstall: () => Promise<InstallOutcome>;
}

const PwaRuntimeContext = createContext<PwaRuntimeContextValue>({
  canPromptInstall: false,
  isInstalled: null,
  isIos: false,
  promptInstall: async () => "unavailable",
});

export function usePwaRuntime(): PwaRuntimeContextValue {
  return useContext(PwaRuntimeContext);
}

export function PwaRegister({
  children,
  buildVersion = "local",
  environment = process.env.NODE_ENV,
}: Readonly<{ children: ReactNode; buildVersion?: string; environment?: string }>) {
  const { showToast } = useToast();
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isInstalled, setIsInstalled] = useState<boolean | null>(null);
  const [isIos, setIsIos] = useState(false);
  const waitingWorkerRef = useRef<ServiceWorker | null>(null);
  const notifiedWorkerRef = useRef<ServiceWorker | null>(null);
  const refreshRequestedRef = useRef(false);
  const reloadStartedRef = useRef(false);

  const activateWaitingWorker = useCallback(() => {
    const worker = waitingWorkerRef.current;
    if (!worker) {
      return;
    }
    refreshRequestedRef.current = true;
    worker.postMessage({ type: "SKIP_WAITING" });
  }, []);

  const announceWaitingWorker = useCallback(
    (worker: ServiceWorker | null) => {
      if (!worker || notifiedWorkerRef.current === worker) {
        return;
      }
      waitingWorkerRef.current = worker;
      notifiedWorkerRef.current = worker;
      showToast("New version available.", {
        durationMs: 0,
        tone: "info",
        action: {
          label: "Refresh",
          onClick: activateWaitingWorker,
        },
      });
    },
    [activateWaitingWorker, showToast],
  );

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
    if (!shouldRegisterServiceWorker(environment, "serviceWorker" in navigator)) {
      return;
    }

    let disposed = false;
    let registration: ServiceWorkerRegistration | null = null;
    let installingWorker: ServiceWorker | null = null;

    const handleControllerChange = () => {
      if (!refreshRequestedRef.current || reloadStartedRef.current) {
        return;
      }
      reloadStartedRef.current = true;
      window.location.reload();
    };

    const handleInstallingStateChange = () => {
      if (
        installingWorker?.state === "installed" &&
        navigator.serviceWorker.controller
      ) {
        announceWaitingWorker(registration?.waiting ?? installingWorker);
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
        announceWaitingWorker(registration.waiting);
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
  }, [announceWaitingWorker, buildVersion, environment]);

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

  const value = useMemo<PwaRuntimeContextValue>(
    () => ({
      canPromptInstall: installPrompt !== null,
      isInstalled,
      isIos,
      promptInstall,
    }),
    [installPrompt, isInstalled, isIos, promptInstall],
  );

  return <PwaRuntimeContext.Provider value={value}>{children}</PwaRuntimeContext.Provider>;
}
