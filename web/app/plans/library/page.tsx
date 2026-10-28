"use client";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { MyCommunitySubmissions } from "@/components/community-exercises";
import { FeaturedDrill } from "@/components/featured-drill";
import styles from "@/components/plans/plans.module.css";
import { TrainingLibrary } from "@/components/training-library";

export default function TrainingLibraryPage() {
  const { session } = useAppSession();
  return <RequireAuth>{session?.access_token ? <div className={styles.page} key={session.access_token}>
    <TrainingLibrary accessToken={session.access_token} />
    <FeaturedDrill accessToken={session.access_token} />
    <section aria-label="Community submissions" className={styles.section}>
      <MyCommunitySubmissions token={session.access_token} />
    </section>
  </div> : null}</RequireAuth>;
}
