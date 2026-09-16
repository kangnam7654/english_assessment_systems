"use client";
import { useState } from "react";
import type { AssessedContent } from "@/lib/api";
import { CriterionCard } from "./criterion-card";
export function AssessmentResult({ result }: { result: AssessedContent }) {
  const [lang, setLang] = useState<"ko" | "en">("ko");
  if (result.schema_version !== "project-1.0")
    return (
      <p className="panel">
        이 화면은 공통 학년별 루브릭 결과를 지원합니다. 이 실행은 이전 점수
        형식입니다.
      </p>
    );
  return (
    <section className="space-y-4" aria-label="평가 결과">
      <div className="flex justify-between items-center">
        <h2 className="font-semibold">영역별 평가</h2>
        <label className="text-sm">
          피드백 언어{" "}
          <select
            className="border rounded p-1"
            value={lang}
            onChange={(e) => setLang(e.target.value as "ko" | "en")}
          >
            <option value="ko">한국어</option>
            <option value="en">English</option>
          </select>
        </label>
      </div>
      <p className="hint">
        영역별 1–4점입니다. 표시값은 정답률이나 학년 간 실력 비교 점수가
        아닙니다.
      </p>
      {result.status === "not_scorable" ? (
        <div className="panel">
          <h3 className="font-semibold">평가 불가</h3>
          <p>
            {result.not_scorable_reason === "non_english"
              ? "영어 글로 평가하기 어렵습니다."
              : "평가할 수 있는 텍스트가 부족합니다."}
          </p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-3">
          {Object.entries(result.per_criterion ?? {}).map(([name, score]) => (
            <CriterionCard
              key={name}
              name={name}
              result={score}
              normalized={result.normalized_scores?.[name] ?? null}
              lang={lang}
            />
          ))}
        </div>
      )}
      {result.source_use_status === "scored" && result.source_use ? (
        <CriterionCard
          name="source_use"
          result={result.source_use}
          normalized={result.source_use_normalized}
          lang={lang}
        />
      ) : (
        <div className="panel text-sm">
          출처 사용 ·{" "}
          {result.source_use_status === "not_applicable"
            ? "적용 안 함"
            : "평가 불가"}
        </div>
      )}
      <div className="panel">
        <h3 className="font-semibold mb-2">종합 피드백</h3>
        <p className="text-sm whitespace-pre-wrap break-words">
          {lang === "ko"
            ? result.summary_feedback_korean
            : result.summary_feedback_english}
        </p>
      </div>
    </section>
  );
}
