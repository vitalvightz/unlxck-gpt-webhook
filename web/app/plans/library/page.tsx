"use client";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { TrainingLibrary } from "@/components/training-library";

export default function TrainingLibraryPage() {
  const { session } = useAppSession();
  return <RequireAuth>{session?.access_token ? <TrainingLibrary key={session.access_token} accessToken={session.access_token} /> : null}</RequireAuth>;
}
