"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import styles from "@/components/starting-path-screen.module.css";

// The one place to start any kind of plan, reached from + Create. Each option
// opens its existing flow; this screen only routes, it saves nothing.
const OPTIONS = [
  { href: "/quick-build", title: "Quick Build", body: "Generate a personalised training programme in minutes." },
  { href: "/onboarding", title: "Full Camp Setup", body: "Build a detailed programme around your fight and training schedule." },
  { href: "/plans/custom", title: "Build Your Own", body: "Create and customise your own training programme." },
] as const;

export default function CreatePage() {
  const router = useRouter();

  function goBack() {
    if (window.history.length > 1) router.back();
    else router.push("/");
  }

  return (
    <RequireAuth>
      <section className={styles.root} aria-labelledby="create-heading">
        <header className={styles.brand}>
          <button className={`${styles.accountAction} ${styles.back}`} type="button" onClick={goBack}>‹ Back</button>
        </header>
        <div className={styles.intro}>
          <h1 id="create-heading">What would you like to create?</h1>
        </div>
        <nav className={styles.choices} aria-label="Create options">
          {OPTIONS.map((option) => (
            <Link key={option.href} href={option.href} className={styles.choice}>
              <span className={styles.copy}><strong>{option.title}</strong><span>{option.body}</span></span>
              <span className={styles.action} aria-hidden="true">›</span>
            </Link>
          ))}
        </nav>
      </section>
    </RequireAuth>
  );
}
