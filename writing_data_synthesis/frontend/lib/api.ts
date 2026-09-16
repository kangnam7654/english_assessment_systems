export type Mode = "synthesis" | "assessment";
export type Grade = `us_${string}`;
export type Genre = "opinion" | "argumentative" | "informative" | "narrative";
export type Level = "beginner" | "intermediate" | "advanced" | "master";
export type ExecutionMode = "mock" | "live" | "unknown";
export interface RubricOption {
  grade: Grade;
  genre: Genre;
  rubric_id: string;
  requires_sources: boolean;
}
export interface RunRequest {
  mode: Mode;
  grade_for_student: Grade;
  grade_for_assessor: Grade;
  genre: Genre;
  rubric_id: "project-writing-v1";
  level: Level;
  user_prompt: string;
  essay?: string;
  source_passages: { source_id: string; text: string }[];
}
export interface CriterionResult {
  score: number;
  comment_english: string;
  comment_korean: string;
}
export interface AssessedContent {
  schema_version: string;
  grade: Grade;
  genre: Genre;
  rubric_id: string;
  status: "scored" | "not_scorable";
  per_criterion: Record<string, CriterionResult> | null;
  normalized_scores: Record<string, number> | null;
  source_use: CriterionResult | null;
  source_use_normalized: number | null;
  source_use_status: "scored" | "not_applicable" | "not_scorable";
  not_scorable_reason: string | null;
  summary_feedback_english: string;
  summary_feedback_korean: string;
}
export interface RunResponse {
  run_id: string;
  stage: string;
  execution_mode: ExecutionMode;
  grade: Grade;
  essay: string | null;
  assessed_content: AssessedContent | null;
  error?: { message: string; code: string } | null;
}
export class ApiError extends Error {
  constructor(
    message: string,
    public runId?: string,
  ) {
    super(message);
  }
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { ...init, cache: "no-store" });
  } catch {
    throw new ApiError(
      "API에 연결할 수 없습니다. 로컬 실행 터미널을 확인해주세요.",
    );
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const message =
      res.status === 404
        ? "저장된 실행을 찾을 수 없습니다."
        : res.status === 422
          ? "입력값을 확인해주세요. 학년·글 유형·과제와 필수 지문이 필요합니다."
          : "요청을 완료하지 못했습니다. 실행 터미널과 저장된 상태를 확인해주세요.";
    throw new ApiError(
      message,
      typeof detail?.run_id === "string" ? detail.run_id : undefined,
    );
  }
  if (!body) throw new ApiError("API 응답을 읽을 수 없습니다.");
  return body as T;
}
export const loadCriteria = () =>
  request<RubricOption[]>("/criteria?family=project");
export const loadRuntime = () =>
  request<{ execution_mode: ExecutionMode }>("/runtime");
export const loadRun = (id: string) =>
  request<RunResponse>(`/runs/${encodeURIComponent(id)}`);
export const runPipeline = (body: RunRequest) =>
  request<RunResponse>("/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
export const gradeLabel = (grade: string) =>
  grade === "us_K"
    ? "유치원 (K)"
    : grade.startsWith("us_")
      ? `${grade.slice(3)}학년`
      : grade;
export const GENRE_LABELS: Record<Genre, string> = {
  opinion: "의견문",
  argumentative: "논증문",
  informative: "정보문",
  narrative: "서사문",
};
export const LEVEL_LABELS: Record<Level, string> = {
  beginner: "초급",
  intermediate: "중급",
  advanced: "고급",
  master: "숙련",
};
export const CRITERION_LABELS: Record<string, string> = {
  task_content: "내용·과제 수행",
  organization: "구성·연결",
  language_expression: "언어 표현",
  conventions: "문법·표기",
  source_use: "출처 사용",
};
