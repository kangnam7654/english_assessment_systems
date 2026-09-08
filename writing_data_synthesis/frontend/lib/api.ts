const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Mode = "synthesis" | "assessment";
export type Grade = "elem_6" | "mid_2" | "high_2";
export type Level = "beginner" | "intermediate" | "advanced" | "master";

export interface RunRequest {
  mode: Mode;
  user_prompt?: string;
  grade_for_student: Grade;
  grade_for_assessor: Grade;
  level: Level;
  essay?: string;
}

export interface CriterionResult {
  score: number;
  comment_english: string;
  comment_korean: string;
}

export interface AssessedContent {
  grade: Grade;
  overall_score: number;
  level: Level;
  per_criterion: Record<string, CriterionResult>;
  summary_feedback_english: string;
  summary_feedback_korean: string;
}

export interface RunResponse {
  grade: Grade | null;
  level: Level | null;
  essay: string | null;
  assessed_content: AssessedContent | null;
}

export async function runPipeline(req: RunRequest): Promise<RunResponse> {
  const res = await fetch(`${API_BASE}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error (${res.status}): ${detail}`);
  }

  return res.json();
}

export const GRADE_LABELS: Record<Grade, string> = {
  elem_6: "Elementary 6th",
  mid_2: "Middle 2nd",
  high_2: "High 2nd",
};

export const LEVEL_LABELS: Record<Level, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
  master: "Master",
};

export const LEVEL_COLORS: Record<Level, string> = {
  beginner: "#ef4444",
  intermediate: "#f59e0b",
  advanced: "#3b82f6",
  master: "#8b5cf6",
};
