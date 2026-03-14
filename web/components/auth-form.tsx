"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition, type FormEvent } from "react";

import { useAppSession } from "@/components/auth-provider";
import { getSupabaseBrowserClient } from "@/lib/supabase";

function inferDemoRole(email: string): "athlete" | "admin" {
  const normalized = email.trim().toLowerCase();
  return normalized.endsWith("@unlxck.test") || normalized.includes("admin") ? "admin" : "athlete";
}

export function AuthForm({ mode }: { mode: "signup" | "login" }) {
  const router = useRouter();
  const { session, demoMode, signInDemo } = useAppSession();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (session) {
      router.replace("/plans");
    }
  }, [router, session]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setError(null);

    startTransition(async () => {
      if (demoMode) {
        const role = inferDemoRole(email);
        await signInDemo(role);
        router.push(mode === "signup" ? "/onboarding" : role === "admin" ? "/admin" : "/plans");
        return;
      }

      let client;
      try {
        client = getSupabaseBrowserClient();
      } catch (clientError) {
        setError(clientError instanceof Error ? clientError.message : "Supabase is not configured.");
        return;
      }

      if (mode === "signup") {
        const { data, error: signUpError } = await client.auth.signUp({
          email,
          password,
          options: {
            data: {
              full_name: fullName,
            },
          },
        });
        if (signUpError) {
          setError(signUpError.message);
          return;
        }
        if (data.session) {
          router.push("/onboarding");
          return;
        }
        setMessage("Check your email to confirm your account, then log in.");
        return;
      }

      const { error: loginError } = await client.auth.signInWithPassword({ email, password });
      if (loginError) {
        setError(loginError.message);
        return;
      }
      router.push("/plans");
    });
  }

  function handleQuickDemo(role: "athlete" | "admin") {
    setMessage(null);
    setError(null);
    startTransition(async () => {
      await signInDemo(role);
      router.push(role === "admin" ? "/admin" : mode === "signup" ? "/onboarding" : "/plans");
    });
  }

  return (
    <section className="auth-layout">
      <div className="auth-rail">
        <div className="hero-panel-copy">
          <p className="eyebrow">{mode === "signup" ? "Free beta" : "Athlete access"}</p>
          <h1>{mode === "signup" ? "Build your camp profile inside UNLXCK." : "Return to your athlete workspace."}</h1>
          <p>
            {mode === "signup"
              ? "Create your account, move through the guided intake, and generate a saved fight camp without leaving the product."
              : "Pick up your onboarding draft, reopen saved plans, and generate the next camp from the same athlete-first workspace."}
          </p>
        </div>
        <div className="support-panel">
          <p className="kicker">Flow</p>
          <ol className="auth-flow">
            <li>Enter your athlete account and keep your intake attached to your profile.</li>
            <li>Move through the structured onboarding with draft save and resume support.</li>
            <li>Generate and reopen your saved plans from one dark-mode control room.</li>
          </ol>
        </div>
        {demoMode ? (
          <div className="support-panel">
            <p className="kicker">Demo mode</p>
            <p className="muted">
              Use any email and password to enter as an athlete, or use an <code>@unlxck.test</code> email to enter the admin view.
            </p>
          </div>
        ) : null}
      </div>

      <div className="auth-card">
        <div className="auth-header">
          <div>
            <p className="kicker">{mode === "signup" ? "Create account" : "Log in"}</p>
            <h2>{mode === "signup" ? "Start the intake" : "Resume your camp"}</h2>
          </div>
          <span className="badge status-badge-neutral">{mode === "signup" ? "Beta" : "Secure"}</span>
        </div>

        {message ? <div className="success-banner">{message}</div> : null}
        {error ? <div className="error-banner">{error}</div> : null}

        <form onSubmit={handleSubmit} className="auth-form-grid">
          {mode === "signup" ? (
            <div className="field">
              <label htmlFor="fullName">Full name</label>
              <input id="fullName" value={fullName} onChange={(event) => setFullName(event.target.value)} required />
            </div>
          ) : null}
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} />
          </div>

          <div className="form-actions">
            <button type="submit" className="cta" disabled={isPending}>
              {isPending ? "Working..." : mode === "signup" ? "Create account" : "Log in"}
            </button>
            <Link href={mode === "signup" ? "/login" : "/signup"} className="ghost-button">
              {mode === "signup" ? "Already have an account?" : "Need an account?"}
            </Link>
          </div>
        </form>

        {demoMode ? (
          <div className="auth-quick-actions">
            <button type="button" className="secondary-button" onClick={() => handleQuickDemo("athlete")}>
              Use demo athlete
            </button>
            <button type="button" className="ghost-button" onClick={() => handleQuickDemo("admin")}>
              Use demo admin
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
