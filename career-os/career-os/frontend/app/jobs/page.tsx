"use client";

import { useState } from "react";
import ErrorNotice from "@/components/ErrorNotice";
import Icon from "@/components/Icon";
import JobSearch from "@/components/JobSearch";
import MatchCard from "@/components/MatchCard";
import PendingDots from "@/components/PendingDots";
import { analyzeJob, ApiError, type MatchResult } from "@/lib/api";

function errorMessage(error: unknown): { code: string; message: string } {
  if (error instanceof ApiError) {
    if (error.code === "RESUME_NOT_FOUND") {
      return { code: error.code, message: "Save your resume before starting an analysis." };
    }
    if (error.code === "AGENT_FAILED" || error.code === "AGENT_UNAVAILABLE") {
      return {
        code: error.code,
        message: "The analysis could not be completed. Your job was saved; you can try again.",
      };
    }
  }
  return {
    code: "UNKNOWN",
    message: "Something went wrong. Check your connection to the server and try again.",
  };
}

export default function JobsPage() {
  const [description, setDescription] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<MatchResult | null>(null);
  const [analysisError, setAnalysisError] = useState<{ code: string; message: string } | null>(null);
  const canAnalyze = description.trim().length > 0 && !analyzing;

  async function handleAnalyze() {
    if (!canAnalyze) return;

    setAnalyzing(true);
    setAnalysisError(null);
    setResult(null);
    try {
      const response = await analyzeJob(description.trim());
      setResult(response.match);
    } catch (error) {
      setAnalysisError(errorMessage(error));
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <div className="animate-rise-in mx-auto max-w-5xl space-y-7">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-indigo-600">Discover</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">Jobs</h1>
        <p className="mt-2 text-sm text-muted">Find relevant opportunities and understand how they fit your resume.</p>
      </header>

      <section className="rounded-2xl border border-line bg-white p-5 shadow-sm transition-shadow duration-200 hover:shadow-md sm:p-6">
        <JobSearch />
      </section>

      <section className="scroll-mt-6 rounded-2xl border border-line bg-white p-5 shadow-sm transition-shadow duration-200 hover:shadow-md sm:p-6">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-600">
            <Icon name="analyze" />
          </span>
          <div>
            <h2 className="text-base font-semibold text-slate-900">Analyze a job</h2>
            <p className="mt-1 text-xs leading-5 text-muted">
              Paste a job description to compare its requirements with your resume and check for potential warning signs.
            </p>
          </div>
        </div>

        <label htmlFor="job-description" className="sr-only">Job description</label>
        <textarea
          id="job-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          disabled={analyzing}
          rows={8}
          placeholder="Paste the full job description here…"
          className="mt-4 w-full rounded-xl border border-line bg-slate-50/70 p-4 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-indigo-400 focus:bg-white disabled:opacity-60"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => void handleAnalyze()}
            disabled={!canAnalyze}
            className="rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {analyzing ? <PendingDots label="Analyzing" /> : (
              <span className="inline-flex items-center gap-2">
                <Icon name="analyze" />
                Analyze job match
              </span>
            )}
          </button>
          {analyzing && <span className="text-xs text-muted">This may take a few seconds.</span>}
        </div>
      </section>

      {analysisError && (
        <ErrorNotice
          code={analysisError.code}
          message={analysisError.message}
          onRetry={() => void handleAnalyze()}
        />
      )}
      {result && (
        <div key={result.id} className="animate-rise-in">
          <MatchCard match={result} />
        </div>
      )}
    </div>
  );
}
