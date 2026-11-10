"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  type CoverLetter,
  createCoverLetter,
  ErrorCode,
  getCoverLetter,
} from "@/lib/api";
import Icon from "./Icon";
import PendingDots from "./PendingDots";

/** CHỈ được render khi `application_status === "approved"` (kiểm tra ở component cha
 * `HistoryList`) — không tự kiểm tra lại ở đây, ẩn hoàn toàn với job khác trạng thái thay vì
 * hiện nhưng disable, tránh gây tò mò bấm thử job chưa approve. */
export default function CoverLetterPanel({ jobId }: { jobId: number }) {
  const [coverLetter, setCoverLetter] = useState<CoverLetter | null>(null);
  const [checking, setChecking] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCoverLetter(jobId)
      .then((result) => {
        if (!cancelled) setCoverLetter(result);
      })
      .catch((err) => {
        // L’absence de lettre créée est un état normal.
        if (err instanceof ApiError && err.code === ErrorCode.COVER_LETTER_NOT_FOUND) return;
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  async function handleGenerate() {
    if (generating) return;
    setGenerating(true);
    setError(null);
    setCopied(false);
    try {
      const result = await createCoverLetter(jobId);
      setCoverLetter(result);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? "Could not generate the cover letter. Check your model provider configuration and try again."
          : "Something went wrong while generating the cover letter. Please try again shortly.",
      );
    } finally {
      setGenerating(false);
    }
  }

  async function handleCopy() {
    if (!coverLetter) return;
    try {
      await navigator.clipboard.writeText(coverLetter.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API có thể bị chặn (permission, context không secure) — im lặng bỏ qua,
      // người dùng vẫn tự select-copy được từ khối text.
    }
  }

  if (checking) {
    return (
      <p className="text-caption text-muted">
        <PendingDots label="Checking for a cover letter" />
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void handleGenerate()}
          disabled={generating}
          className="rounded-control bg-accent px-4 py-2 text-caption font-semibold text-white transition duration-150 ease-out-soft hover:bg-accent-hover hover:scale-[1.02] disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-50 disabled:hover:scale-100"
        >
          {generating ? (
            <PendingDots label="Generating" />
          ) : coverLetter ? (
            <span className="inline-flex items-center gap-2">
              <Icon name="refresh" />
              Regenerate
            </span>
          ) : (
            <span className="inline-flex items-center gap-2">
              <Icon name="analyze" />
              Generate cover letter
            </span>
          )}
        </button>
        {coverLetter && (
          <button
            type="button"
            onClick={() => void handleCopy()}
            className="rounded-control border border-line bg-surface px-4 py-2 text-caption font-semibold text-content transition duration-150 ease-out-soft hover:bg-surface-muted hover:scale-[1.02]"
          >
            <span className="inline-flex items-center gap-2">
              <Icon name={copied ? "check" : "copy"} />
              {copied ? "Copied" : "Copy"}
            </span>
          </button>
        )}
      </div>

      {error && (
        <p role="alert" className="text-caption font-semibold text-verdict-weak">
          {error}
        </p>
      )}

      {coverLetter && (
        <div className="whitespace-pre-wrap rounded-card border border-line bg-surface-muted p-4 text-body text-content">
          {coverLetter.content}
        </div>
      )}
    </div>
  );
}
