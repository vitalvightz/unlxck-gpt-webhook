"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

import { submitGlobalFeedback } from "@/lib/api";
import type { GlobalFeedbackRequest } from "@/lib/types";

const CATEGORIES: Array<{ value: GlobalFeedbackRequest["category"]; label: string }> = [
  { value: "bug_report", label: "Report a bug" },
  { value: "feature_request", label: "Request a feature" },
  { value: "safety_issue", label: "Report a safety issue" },
  { value: "general_feedback", label: "General feedback" },
];

function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
}

export function GlobalFeedback({ token }: Readonly<{ token: string }>) {
  const [category, setCategory] = useState<GlobalFeedbackRequest["category"]>("bug_report");
  const [description, setDescription] = useState("");
  const [contactAllowed, setContactAllowed] = useState(false);
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  function selectScreenshot(file: File | null) {
    setScreenshot(file);
    setPreviewUrl(file ? URL.createObjectURL(file) : null);
  }

  function removeScreenshot() {
    setScreenshot(null);
    setPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      await submitGlobalFeedback(token, {
        category,
        description,
        contact_allowed: contactAllowed,
        screenshot,
      });
      setDescription("");
      removeScreenshot();
      setContactAllowed(false);
      setMessage("Feedback sent. Thank you.");
      form.reset();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Feedback could not be sent. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="global-feedback-form" onSubmit={submit}>
      <div className="feedback-category-grid" role="radiogroup" aria-label="Feedback category">
        {CATEGORIES.map((item) => (
          <button
            key={item.value}
            type="button"
            role="radio"
            aria-checked={category === item.value}
            className={category === item.value ? "feedback-category is-selected" : "feedback-category"}
            onClick={() => setCategory(item.value)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="field">
        <label htmlFor="global-feedback-description">Optional description</label>
        <textarea
          id="global-feedback-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          maxLength={500}
          rows={4}
        />
        <span className="muted feedback-counter">{description.length}/500</span>
      </div>
      <div className="field">
        <label htmlFor="global-feedback-screenshot">Optional screenshot</label>
        <input
          ref={fileInputRef}
          id="global-feedback-screenshot"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => selectScreenshot(event.target.files?.[0] ?? null)}
        />
        <p className="feedback-privacy-copy">
          Avoid uploading screenshots containing private messages, contact details, payment information, or unrelated health information.
        </p>
        <p className="feedback-privacy-copy">
          Sanitisation removes metadata. It does not remove sensitive information visible inside the image.
        </p>
        {screenshot && previewUrl ? (
          <div className="feedback-attachment-preview">
            <Image
              src={previewUrl}
              alt="Selected screenshot preview"
              width={640}
              height={360}
              unoptimized
            />
            <div className="feedback-attachment-meta">
              <span>
                <strong>{screenshot.name}</strong>
                <span className="muted">{formatFileSize(screenshot.size)}</span>
              </span>
              <button type="button" className="ghost-button" onClick={removeScreenshot}>
                Remove image
              </button>
            </div>
          </div>
        ) : null}
      </div>
      <label className="settings-toggle-row feedback-contact-row">
        <span>
          <span className="settings-toggle-title">You may contact me about this</span>
          <span className="settings-toggle-detail">Allow the beta team to follow up.</span>
        </span>
        <input
          type="checkbox"
          checked={contactAllowed}
          onChange={(event) => setContactAllowed(event.target.checked)}
        />
      </label>
      <div className="feedback-submit-row">
        <button type="submit" className="cta" disabled={submitting}>
          {submitting ? "Sending…" : "Send feedback"}
        </button>
      </div>
      {message ? <p className="success-banner" role="status">{message}</p> : null}
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
    </form>
  );
}
