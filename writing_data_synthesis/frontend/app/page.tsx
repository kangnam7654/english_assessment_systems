"use client";

import { useState } from "react";
import { InputForm } from "@/components/input-form";
import { EssayOutput } from "@/components/essay-output";
import { AssessmentResult } from "@/components/assessment-result";
import {
  type Mode,
  type Grade,
  type Level,
  type AssessedContent,
  runPipeline,
} from "@/lib/api";
import { GraduationCap, AlertCircle } from "lucide-react";

export default function Home() {
  const [mode, setMode] = useState<Mode>("synthesis");
  const [gradeForStudent, setGradeForStudent] = useState<Grade>("mid_2");
  const [gradeForAssessor, setGradeForAssessor] = useState<Grade>("mid_2");
  const [level, setLevel] = useState<Level>("intermediate");
  const [userPrompt, setUserPrompt] = useState("");
  const [essayInput, setEssayInput] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [essayResult, setEssayResult] = useState<string | null>(null);
  const [assessmentResult, setAssessmentResult] =
    useState<AssessedContent | null>(null);

  const handleSubmit = async () => {
    setError(null);
    setLoading(true);

    try {
      const res = await runPipeline({
        mode,
        user_prompt: mode === "synthesis" ? userPrompt : undefined,
        grade_for_student: gradeForStudent,
        grade_for_assessor: gradeForAssessor,
        level,
        essay: mode === "assessment" ? essayInput : undefined,
      });

      setEssayResult(res.essay ?? null);
      setAssessmentResult(res.assessed_content ?? null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "An unexpected error occurred"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-border bg-card/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center gap-3">
          <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center">
            <GraduationCap size={22} className="text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-lg font-bold">English Writing Assessment</h1>
            <p className="text-xs text-muted-foreground">
              Multi-Agent Essay Generation & Evaluation System
            </p>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left: Input Panel */}
          <div className="lg:col-span-4">
            <div className="bg-card rounded-2xl border border-border p-5 sticky top-24">
              <h2 className="font-semibold text-base mb-4">Configuration</h2>
              <InputForm
                mode={mode}
                gradeForStudent={gradeForStudent}
                gradeForAssessor={gradeForAssessor}
                level={level}
                userPrompt={userPrompt}
                essayInput={essayInput}
                loading={loading}
                onModeChange={setMode}
                onGradeForStudentChange={setGradeForStudent}
                onGradeForAssessorChange={setGradeForAssessor}
                onLevelChange={setLevel}
                onUserPromptChange={setUserPrompt}
                onEssayInputChange={setEssayInput}
                onSubmit={handleSubmit}
              />
            </div>
          </div>

          {/* Right: Results Panel */}
          <div className="lg:col-span-8 space-y-6">
            {/* Error */}
            {error && (
              <div className="flex items-start gap-3 bg-red-50 border border-red-200 text-red-800 rounded-xl p-4 animate-fade-in">
                <AlertCircle size={18} className="mt-0.5 shrink-0" />
                <div>
                  <p className="font-semibold text-sm">Error</p>
                  <p className="text-sm mt-0.5">{error}</p>
                </div>
              </div>
            )}

            {/* Empty state */}
            {!loading && !essayResult && !assessmentResult && !error && (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="w-16 h-16 bg-muted rounded-2xl flex items-center justify-center mb-4">
                  <GraduationCap size={28} className="text-muted-foreground" />
                </div>
                <h3 className="font-semibold text-muted-foreground">
                  Ready to Assess
                </h3>
                <p className="text-sm text-muted-foreground mt-1 max-w-sm">
                  Configure the settings on the left and click &quot;Run
                  Assessment&quot; to generate and evaluate an English essay.
                </p>
              </div>
            )}

            {/* Loading state */}
            {loading && (
              <div className="flex flex-col items-center justify-center py-20 text-center animate-fade-in">
                <div className="w-12 h-12 border-4 border-muted border-t-primary rounded-full animate-spin mb-4" />
                <h3 className="font-semibold text-muted-foreground">
                  Processing...
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                  The AI agents are working on your request. This may take a
                  moment.
                </p>
              </div>
            )}

            {/* Essay Output */}
            {!loading && essayResult && <EssayOutput essay={essayResult} />}

            {/* Assessment Result */}
            {!loading && assessmentResult && (
              <AssessmentResult result={assessmentResult} />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
