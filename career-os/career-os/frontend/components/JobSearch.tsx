"use client";

import { useState } from "react";
import { ApiError, searchJobs, type Job } from "@/lib/api";
import PendingDots from "./PendingDots";
import SourceBadge from "./SourceBadge";

/**
 * Ô tìm kiếm theo ý nghĩa (Phase 3 việc #4 mục 6) — RIÊNG BIỆT với textarea dán JD ở dưới, gõ ý
 * muốn tìm bằng ngôn ngữ tự nhiên thay vì từ khóa chính xác. Tái dùng đúng style card từ
 * `HistoryList.tsx` (title, badge nguồn, ngày, link, excerpt) — không thiết kế mới, chỉ bỏ phần
 * match/scam/status vì kết quả tìm kiếm là `Job` thô, không có `match`.
 *
 * KHÔNG hiện điểm similarity thô — con số cosine không có ý nghĩa trực quan với người dùng, chỉ
 * thứ tự kết quả (đã sắp theo gần nghĩa nhất) là đủ.
 */

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function excerpt(text: string, max = 150) {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

export default function JobSearch() {
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canSearch = query.trim().length > 0 && !searching;

  async function handleSearch() {
    if (!canSearch) return;

    setSearching(true);
    setError(null);

    try {
      setResults(await searchJobs(query.trim()));
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Đã có lỗi xảy ra khi tìm kiếm. Thử lại sau ít phút.",
      );
      setResults(null);
    } finally {
      setSearching(false);
    }
  }

  return (
    <section>
      <h2 className="font-display text-body font-semibold tracking-tight">
        Tìm job theo ý nghĩa
      </h2>
      <p className="mt-1 text-caption text-muted">
        Gõ điều bạn muốn tìm bằng ngôn ngữ tự nhiên, không cần đúng từ khóa.
      </p>

      <div className="mt-3 flex flex-wrap gap-3">
        <label htmlFor="job-search-input" className="sr-only">
          Tìm job theo ý nghĩa
        </label>
        <input
          id="job-search-input"
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void handleSearch();
          }}
          disabled={searching}
          placeholder="Ví dụ: việc data engineer cho fresher, làm với Kubernetes…"
          className="min-w-0 flex-1 rounded-control border border-line bg-surface px-4 py-2.5 text-body outline-none transition-colors duration-150 placeholder:text-muted focus:border-accent disabled:opacity-60"
        />
        <button
          type="button"
          onClick={() => void handleSearch()}
          disabled={!canSearch}
          className="rounded-control bg-accent px-5 py-2.5 font-display text-body font-semibold text-white transition duration-150 ease-out-soft hover:bg-accent-hover hover:scale-[1.02] disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-50 disabled:hover:scale-100"
        >
          {searching ? <PendingDots label="Đang tìm" /> : "Tìm"}
        </button>
      </div>

      {error && <p className="mt-3 text-caption text-verdict-weak">{error}</p>}

      {results && (
        <div className="mt-4">
          {results.length === 0 ? (
            <p className="text-body text-muted">
              Không tìm thấy job nào khớp — thử diễn đạt khác xem sao.
            </p>
          ) : (
            <ul className="space-y-3">
              {results.map((job) => (
                <li
                  key={job.id}
                  className="animate-rise-in rounded-card border border-line bg-surface p-5 shadow-card transition duration-150 ease-out-soft hover:bg-surface-muted"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-display text-body font-semibold">
                          {job.title ?? `Job #${job.id}`}
                        </p>
                        <SourceBadge source={job.source} />
                      </div>
                      <p className="mt-1 text-caption text-muted">{formatDate(job.created_at)}</p>
                      {job.url && (
                        <a
                          href={job.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-1 inline-flex items-center gap-1 text-caption font-semibold text-accent hover:underline"
                        >
                          Xem tin gốc &amp; tự ứng tuyển ↗
                        </a>
                      )}
                    </div>
                  </div>
                  <p className="mt-3 text-body text-muted">{excerpt(job.description)}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
