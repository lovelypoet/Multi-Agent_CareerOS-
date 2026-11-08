"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import PendingDots from "@/components/PendingDots";
import {
  ApiError,
  type CVExtractedKeywords,
  ErrorCode,
  getExtractedKeywords,
  getResume,
  saveResume,
  uploadResumePdf,
} from "@/lib/api";

export default function ResumePage() {
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [extractedKeywords, setExtractedKeywords] = useState<CVExtractedKeywords | null>(null);

  // Trích xuất chạy ĐỒNG BỘ ngay trong request lưu resume (xem BE) — gọi lại GET này sau khi
  // save/upload thành công là đủ để lấy kết quả mới nhất, không cần polling.
  async function refreshExtractedKeywords() {
    try {
      setExtractedKeywords(await getExtractedKeywords());
    } catch {
      // Chưa có (404, vd trích xuất lần đầu chưa từng chạy hoặc lỗi) — không hiện khối minh
      // bạch, không phải lỗi cần báo cho người dùng thấy.
      setExtractedKeywords(null);
    }
  }

  useEffect(() => {
    // Chưa có resume (404) là trạng thái bình thường ở lần dùng đầu tiên, không phải lỗi.
    getResume()
      .then((resume) => setContent(resume.content))
      .catch((err) => {
        if (!(err instanceof ApiError) || err.code !== ErrorCode.RESUME_NOT_FOUND) {
          setError("Could not load your saved resume. You can paste new content and save it.");
        }
      })
      .finally(() => setLoading(false));

    void refreshExtractedKeywords();
  }, []);

  const canSave = content.trim().length > 0 && !saving;

  async function handleSave() {
    if (!canSave) return;

    setSaving(true);
    setError(null);
    setSaved(false);

    try {
      await saveResume(content.trim());
      setSaved(true);
      // Trích xuất đã chạy xong đồng bộ trong request lưu ở trên — gọi lại ngay để lấy kết quả
      // mới nhất (hoặc giữ nguyên khối cũ nếu lần này lỗi, BE không xoá dữ liệu cũ).
      await refreshExtractedKeywords();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? "Could not save your resume. Check the server and try again."
          : "Something went wrong while saving. Check your connection and try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleUploadPdf(file: File) {
    if (uploading) return;

    setUploading(true);
    setError(null);
    setSaved(false);

    try {
      const resume = await uploadResumePdf(file);
      // Đổ text đã trích ra vào textarea — người dùng thấy ngay kết quả, có thể sửa tay
      // tiếp nếu muốn, giống hệt cảm giác dán tay.
      setContent(resume.content);
      setSaved(true);
      await refreshExtractedKeywords();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? "Could not process this PDF. Check the file format and size, then try again."
          : "Something went wrong while uploading the PDF. Check your connection and try again.",
      );
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="font-display text-section-lg font-bold tracking-tight">My Resume</h1>
        <p className="mt-3 text-body-lg text-muted">
          Paste your resume text or upload a PDF. Your saved resume will be used to analyze jobs.
        </p>
      </section>

      {loading ? (
        <p className="text-body text-muted">
          <PendingDots label="Loading resume" />
        </p>
      ) : (
        <section>
          <label htmlFor="resume-content" className="sr-only">
            Resume content
          </label>
          <textarea
            id="resume-content"
            value={content}
            onChange={(event) => {
              setContent(event.target.value);
              setSaved(false);
            }}
            disabled={saving}
            rows={18}
            placeholder="Paste your resume content here…"
            className="w-full rounded-card border border-line bg-surface p-5 text-body shadow-card outline-none transition-colors duration-150 placeholder:text-muted focus:border-accent disabled:opacity-60"
          />

          <div className="mt-4 flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave}
              className="rounded-control bg-accent px-6 py-3 font-display text-body font-semibold text-white transition duration-150 ease-out-soft hover:bg-accent-hover hover:scale-[1.02] disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-50 disabled:hover:scale-100"
            >
              {saving ? <PendingDots label="Saving…" /> : "Save resume"}
            </button>

            {saved && (
              <span className="animate-rise-in text-caption font-semibold text-verdict-strong">
                Resume saved. <Link href="/" className="underline">Return to pipeline</Link>
              </span>
            )}
          </div>

          <div className="my-6 flex items-center gap-4 text-caption text-muted">
            <span className="h-px flex-1 bg-line" />
            or upload a PDF
            <span className="h-px flex-1 bg-line" />
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <label
              htmlFor="resume-pdf-upload"
              className={`rounded-control border border-line bg-surface px-6 py-3 font-display text-body font-semibold text-content transition duration-150 ease-out-soft hover:bg-surface-muted ${
                uploading ? "cursor-not-allowed opacity-60" : "cursor-pointer"
              }`}
            >
              {uploading ? <PendingDots label="Processing PDF" /> : "Choose a PDF file"}
            </label>
            <input
              ref={fileInputRef}
              id="resume-pdf-upload"
              type="file"
              accept="application/pdf"
              disabled={uploading}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleUploadPdf(file);
              }}
              className="sr-only"
            />
            <span className="text-caption text-muted">5 MB maximum. Scanned PDFs without selectable text are not supported.</span>
          </div>

          {error && (
            <p role="alert" className="mt-4 text-body font-semibold text-verdict-weak">
              {error}
            </p>
          )}

          {extractedKeywords &&
            (extractedKeywords.domains.length > 0 || extractedKeywords.key_skills.length > 0) && (
              <div className="mt-6 rounded-card border border-line bg-surface-muted p-4">
                <p className="text-caption font-semibold text-muted">
                  Skills identified in your resume and used to improve job search filters:
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {[...extractedKeywords.domains, ...extractedKeywords.key_skills].map((keyword) => (
                    <span
                      key={keyword}
                      className="rounded-full bg-accent-subtle px-2.5 py-1 text-[12px] font-semibold text-accent"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              </div>
            )}
        </section>
      )}
    </div>
  );
}
