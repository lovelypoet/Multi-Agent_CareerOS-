/**
 * Lớp gọi API duy nhất của FE. Component không tự gọi fetch để mọi lỗi được chuẩn hoá
 * về cùng một dạng (có `code`) trước khi tới UI.
 */

export type Verdict = "strong_match" | "good_match" | "partial_match" | "weak_match";
export type JobSource = "manual" | "itviec";
export type ApplicationStatus = "pending" | "approved" | "rejected" | "applied";
// Phase 2 chỉ được ghi 2 giá trị này — 'pending' (không có row) và 'applied' (Phase 3+)
// không có đường nào được phép gửi lên từ FE.
export type UpdatableApplicationStatus = "approved" | "rejected";
// Suy ra từ dữ liệu ở BE, không phải cột riêng. "needs_review" = 2 model (ensemble) bất đồng
// verdict, cần người xem lại thủ công — xem AgentRunsDetail.tsx.
export type AnalysisStatus = "analyzed" | "failed" | "needs_review" | "pending";

export type RiskLevel = "low" | "medium" | "high";
// TÁCH RIÊNG khỏi AnalysisStatus dù trùng 4 giá trị — 2 agent độc lập (matching, scam_detection),
// 2 trạng thái độc lập, không gộp chung 1 field (xem BE `schemas/job.py`).
export type ScamCheckStatus = "analyzed" | "failed" | "needs_review" | "pending";

export interface Job {
  id: number;
  title: string | null;
  company: string | null;
  url: string | null;
  description: string;
  source: JobSource;
  created_at: string;
}

// Phase 3 việc #1 (giai đoạn 1) — Gmail monitoring, chỉ đọc & phân loại.
export type EmailCategory =
  | "rejection"
  | "interview_invite"
  | "follow_up_question"
  | "other_relevant";

export interface EmailNotification {
  id: number;
  account_email: string;
  gmail_message_id: string;
  is_relevant: boolean;
  job_id: number | null;
  category: EmailCategory | null;
  company_name_mentioned: string | null;
  summary: string;
  sender: string;
  subject: string;
  received_at: string;
  created_at: string;
}

export interface EmailNotificationWithJob {
  notification: EmailNotification;
  job: Job | null;
}

export interface MatchResult {
  id: number;
  job_id: number;
  resume_id: number;
  score: number;
  verdict: Verdict;
  reasoning: string;
  matched_requirements: string[];
  missing_requirements: string[];
  suggestions: string[];
  created_at: string;
}

export interface ScamAssessment {
  id: number;
  job_id: number;
  is_suspicious: boolean;
  risk_level: RiskLevel;
  red_flags: string[];
  reasoning: string;
  created_at: string;
}

export interface JobWithMatch {
  job: Job;
  match: MatchResult | null;
  application_status: ApplicationStatus;
  analysis_status: AnalysisStatus;
  // Độc lập hoàn toàn với match/analysis_status — 2 agent chạy độc lập, không cái nào chặn cái
  // nào (xem BE `api/jobs.py::analyze_job`).
  scam: ScamAssessment | null;
  scam_check_status: ScamCheckStatus;
}

export interface AgentRunDetail {
  id: number;
  model: string | null;
  prompt_version: string;
  output: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
}

export interface ApplicationUpdateResult {
  job_id: number;
  status: ApplicationStatus;
  updated_at: string;
}

export interface DashboardSummary {
  jobs_today: number;
  approved_count: number;
  // null khi chưa có match_result nào — FE phải hiện "—", không phải "NaN".
  avg_score: number | null;
}

export interface AnalyzeResponse {
  job: Job;
  // null khi ensemble bất đồng verdict (needs_review) — job vẫn được lưu, chỉ là chưa có
  // match_result đáng tin để trả về ngay.
  match: MatchResult | null;
}

export interface Resume {
  id: number;
  content: string;
  created_at: string;
}

// Phase 3 việc #4 (giai đoạn 1) — CV extraction agent, bổ sung bộ lọc Phase 1.
export interface CVExtractedKeywords {
  resume_id: number;
  domains: string[];
  key_skills: string[];
  updated_at: string;
  created_at: string;
}

export interface CoverLetter {
  id: number;
  job_id: number;
  resume_id: number;
  content: string;
  created_at: string;
}

export const ErrorCode = {
  RESUME_NOT_FOUND: "RESUME_NOT_FOUND",
  AGENT_FAILED: "AGENT_FAILED",
  AGENT_UNAVAILABLE: "AGENT_UNAVAILABLE",
  AGENT_MISCONFIGURED: "AGENT_MISCONFIGURED",
  JOB_NOT_FOUND: "JOB_NOT_FOUND",
  PDF_TOO_LARGE: "PDF_TOO_LARGE",
  PDF_NOT_A_PDF: "PDF_NOT_A_PDF",
  PDF_ENCRYPTED: "PDF_ENCRYPTED",
  PDF_EMPTY_TEXT: "PDF_EMPTY_TEXT",
  PDF_PARSE_FAILED: "PDF_PARSE_FAILED",
  APPLICATION_NOT_APPROVED: "APPLICATION_NOT_APPROVED",
  COVER_LETTER_NOT_FOUND: "COVER_LETTER_NOT_FOUND",
  CV_KEYWORDS_NOT_FOUND: "CV_KEYWORDS_NOT_FOUND",
  SEARCH_UNAVAILABLE: "SEARCH_UNAVAILABLE",
  NETWORK: "NETWORK",
  UNKNOWN: "UNKNOWN",
} as const;

export type ErrorCodeValue = (typeof ErrorCode)[keyof typeof ErrorCode];

export class ApiError extends Error {
  code: ErrorCodeValue | string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/**
 * Backend trả lỗi ở 2 dạng:
 *  - lỗi nghiệp vụ:      { detail: { code, message } }
 *  - lỗi validate (422):  { detail: [ {...}, ... ] }
 * Hàm này quy về một dạng để UI chỉ phải xử lý một kiểu.
 */
async function toApiError(response: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    return new ApiError(
      ErrorCode.UNKNOWN,
      "Máy chủ trả về phản hồi không đọc được.",
      response.status,
    );
  }

  const detail = (payload as { detail?: unknown })?.detail;

  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const info = detail as { code?: string; message?: string };
    return new ApiError(
      info.code ?? ErrorCode.UNKNOWN,
      info.message ?? "Đã có lỗi xảy ra.",
      response.status,
    );
  }

  if (Array.isArray(detail)) {
    return new ApiError(
      "VALIDATION_ERROR",
      "Dữ liệu gửi lên không hợp lệ. Kiểm tra lại nội dung đã nhập.",
      response.status,
    );
  }

  return new ApiError(ErrorCode.UNKNOWN, "Đã có lỗi xảy ra.", response.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      ErrorCode.NETWORK,
      "Không kết nối được tới máy chủ. Kiểm tra backend đã chạy chưa.",
      0,
    );
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  return (await response.json()) as T;
}

export function analyzeJob(description: string): Promise<AnalyzeResponse> {
  return request<AnalyzeResponse>("/api/jobs/analyze", {
    method: "POST",
    body: JSON.stringify({ description }),
  });
}

export function listJobs(): Promise<JobWithMatch[]> {
  return request<JobWithMatch[]>("/api/jobs");
}

export function saveResume(content: string): Promise<Resume> {
  return request<Resume>("/api/resume", {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function getResume(): Promise<Resume> {
  return request<Resume>("/api/resume");
}

export function getExtractedKeywords(): Promise<CVExtractedKeywords> {
  return request<CVExtractedKeywords>("/api/resume/extracted-keywords");
}

/**
 * Upload CV dạng PDF. KHÔNG được gọi qua `request()` ở trên — hàm đó set cứng
 * `Content-Type: application/json` cho mọi request.
 *
 * Cũng KHÔNG tự set `Content-Type` cho request này dù biết tên đúng là
 * `multipart/form-data`: nếu không set gì, `fetch` tự sinh `Content-Type` kèm đúng
 * `boundary`; tự set tay sẽ thiếu `boundary` và server không parse được multipart, dù
 * Content-Type nhìn qua tưởng đúng (đã tự tay verify bug này).
 */
export async function uploadResumePdf(file: File): Promise<Resume> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/resume/upload`, {
      method: "POST",
      body: formData,
    });
  } catch {
    throw new ApiError(
      ErrorCode.NETWORK,
      "Không kết nối được tới máy chủ. Kiểm tra backend đã chạy chưa.",
      0,
    );
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  return (await response.json()) as Resume;
}

export function updateApplicationStatus(
  jobId: number,
  status: UpdatableApplicationStatus,
): Promise<ApplicationUpdateResult> {
  return request<ApplicationUpdateResult>(`/api/jobs/${jobId}/application`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/api/dashboard/summary");
}

/**
 * `agentName` tuỳ chọn — lọc chỉ lấy row của đúng agent đó (vd. "scam_detection_agent"), cần
 * thiết từ khi có >1 agent cùng khả năng rơi vào needs_review (matching, scam). Không truyền
 * thì trả TOÀN BỘ agent_runs của job như hành vi cũ (tương thích ngược).
 */
export function getJobAgentRuns(jobId: number, agentName?: string): Promise<AgentRunDetail[]> {
  const query = agentName ? `?agent_name=${encodeURIComponent(agentName)}` : "";
  return request<AgentRunDetail[]>(`/api/jobs/${jobId}/agent-runs${query}`);
}

export function createCoverLetter(jobId: number): Promise<CoverLetter> {
  return request<CoverLetter>(`/api/jobs/${jobId}/cover-letter`, { method: "POST" });
}

export function getCoverLetter(jobId: number): Promise<CoverLetter> {
  return request<CoverLetter>(`/api/jobs/${jobId}/cover-letter`);
}

export function getEmailNotifications(): Promise<EmailNotificationWithJob[]> {
  return request<EmailNotificationWithJob[]>("/api/email-notifications");
}

/**
 * Tìm kiếm job theo ý nghĩa (Phase 3 việc #4 mục 5) — `q` là câu tự nhiên, không phải từ khóa
 * chính xác. Chỉ trả job đã có embedding — job cũ trước tính năng này sẽ không xuất hiện.
 */
export function searchJobs(q: string): Promise<Job[]> {
  return request<Job[]>(`/api/jobs/search?q=${encodeURIComponent(q)}`);
}
