"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  createPwaWorkerUrl,
  isIosDevice,
  isStandaloneDisplay,
  PWA_DISPLAY_MODE_QUERY,
  resolvePwaInstallAvailability,
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

export function usePwaRuntime(): PwaRuntimeContextValue {
  return useContext(PwaRuntimeContext);
}

export function PwaRegister({
  children,
  buildVersion = "local",
  environment = process.env.NODE_ENV,
}: Readonly<{
  children: ReactNode;
  buildVersion?: string;
  environment?: string;
}>) {
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isInstalled, setIsInstalled] = useState<boolean | null>(null);
  const [isIos, setIsIos] = useState(false);

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

    const workerUrl = createPwaWorkerUrl(buildVersion);

    void navigator.serviceWorker
      .register(workerUrl, { scope: "/", updateViaCache: "none" })
      .catch(() => {
        // PWA support is progressive enhancement; registration failures must
        // never block auth, navigation, intake, or plan generation.
      });

  }, [buildVersion, environment]);

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
