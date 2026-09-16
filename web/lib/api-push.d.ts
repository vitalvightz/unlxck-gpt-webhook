import "@/lib/api";

declare module "@/lib/api" {
  interface PushSettingsResponse {
    subscription_endpoints: string[] | null;
  }
}
