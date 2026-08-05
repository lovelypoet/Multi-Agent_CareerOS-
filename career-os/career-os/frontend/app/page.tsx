"use client";

import { useCallback, useEffect, useState } from "react";
import Dashboard from "@/components/Dashboard";
import ErrorNotice from "@/components/ErrorNotice";
import HistoryList from "@/components/HistoryList";
import MatchCard from "@/components/MatchCard";
import PendingDots from "@/components/PendingDots";
import { analyzeJob, ApiError, listJobs, type JobWithMatch, type MatchResult } from "@/lib/api";

export default function AnalyzePage() {
  const [description, setDescription] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<MatchResult | null>(null);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);

  const [history, setHistory] = useState<JobWithMatch[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await listJobs());
    } catch {
      // Lỗi tải lịch sử không được che mất kết quả phân tích vừa chạy xong.
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  const canAnalyze = description.trim().length > 0 && !analyzing;

  async function handleAnalyze() {
    // Chặn cả trường hợp bấm lần 2 khi request trước chưa xong (tránh tạo job trùng, tốn phí API).
    if (!canAnalyze) return;

    setAnalyzing(true);
    setError(null);
    setResult(null);

    try {
      const response = await analyzeJob(description.trim());
      setResult(response.match);
      // Lịch sử tự cập nhật ngay, không bắt user F5.
      await refreshHistory();
    } catch (err) {
      const apiError =
        err instanceof ApiError
          ? { code: apiErrorCode(err), message: err.message }
          : { code: "UNKNOWN", message: "Đã có lỗi xảy ra. Thử lại sau ít phút." };
      setError(apiError);
      // Job vẫn có thể đã được lưu ở BE — làm mới lịch sử để phản ánh đúng thực tế.
      await refreshHistory();
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <div className="space-y-14">
      <section>
        <Dashboard />
      </section>

      <section>
        <h1 className="font-display text-section-lg font-bold tracking-tight">
          Job cho bạn hôm nay
        </h1>
        <p className="mt-3 text-body-lg text-muted">
          Job mới tự động tìm thấy mỗi ngày, đã chấm điểm sẵn — cùng lịch sử các job bạn đã phân
          tích.
        </p>
        <div className="mt-6">
          {historyLoading ? (
            <p className="text-body text-muted">
              <PendingDots label="Đang tải lịch sử" />
            </p>
          ) : (
            <HistoryList items={history} />
          )}
        </div>
      </section>

      <section className="rounded-card border border-line bg-surface-muted p-6">
        <h2 className="font-display text-body font-semibold tracking-tight">
          Tìm thấy job ở nơi khác? Dán JD vào đây để kiểm tra phù hợp
        </h2>

        <div className="mt-4">
          <label htmlFor="job-description" className="sr-only">
            Mô tả công việc
          </label>
          <textarea
            id="job-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            disabled={analyzing}
            rows={12}
            placeholder="Dán toàn bộ mô tả công việc vào đây…"
            className="w-full rounded-card border border-line bg-surface p-5 text-body shadow-card outline-none transition-colors duration-150 placeholder:text-muted focus:border-accent disabled:opacity-60"
          />

          <div className="mt-4 flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={!canAnalyze}
              className="rounded-control bg-accent px-6 py-3 font-display text-body font-semibold text-white transition duration-150 ease-out-soft hover:bg-accent-hover hover:scale-[1.02] disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-50 disabled:hover:scale-100"
            >
              {analyzing ? <PendingDots label="Đang phân tích" /> : "Chấm điểm phù hợp"}
            </button>

            {analyzing && (
              <span className="text-caption text-muted">
                Thường mất vài giây. Đừng đóng tab này.
              </span>
            )}
          </div>
        </div>
      </section>

      {error && (
        <ErrorNotice code={error.code} message={error.message} onRetry={() => void handleAnalyze()} />
      )}

      {result && (
        <section>
          <h2 className="sr-only">Kết quả phân tích</h2>
          <MatchCard match={result} />
        </section>
      )}
    </div>
  );
}

function apiErrorCode(error: ApiError): string {
  return typeof error.code === "string" ? error.code : "UNKNOWN";
}
