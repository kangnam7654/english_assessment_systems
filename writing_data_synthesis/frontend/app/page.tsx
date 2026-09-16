"use client";
import { useEffect, useState, useRef } from "react";
import { InputForm } from "@/components/input-form";
import { EssayOutput } from "@/components/essay-output";
import { AssessmentResult } from "@/components/assessment-result";
import {
  ApiError,
  loadCriteria,
  loadRuntime,
  loadRun,
  runPipeline,
  gradeLabel,
  GENRE_LABELS,
  type ExecutionMode,
  type RubricOption,
  type RunResponse,
  type RunRequest,
} from "@/lib/api";

export default function Home() {
  const [options, setOptions] = useState<RubricOption[]>([]);
  const [runtime, setRuntime] = useState<ExecutionMode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failedId, setFailedId] = useState<string | null>(null);
  const [result, setResult] = useState<RunResponse | null>(null);
  const [lookup, setLookup] = useState("");
  const [recent, setRecent] = useState<string[]>([]);
  const busy = useRef(false);
  useEffect(() => {
    let active = true;
    Promise.all([loadCriteria(), loadRuntime()])
      .then(([criteria, info]) => {
        if (active) {
          setOptions(criteria);
          setRuntime(info.execution_mode);
        }
      })
      .catch(() => {
        if (active) {
          setRuntime("unknown");
          setError(
            "초기 정보를 불러오지 못했습니다. API 실행을 확인하고 페이지를 새로고침해주세요.",
          );
        }
      });
    return () => {
      active = false;
    };
  }, []);
  async function execute(action: () => Promise<RunResponse>) {
    if (busy.current) return;
    busy.current = true;
    setLoading(true);
    setError(null);
    setFailedId(null);
    setResult(null);
    try {
      const response = await action();
      setResult(response);
      setLookup(response.run_id);
      setRecent((ids) =>
        [response.run_id, ...ids.filter((id) => id !== response.run_id)].slice(
          0,
          10,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "요청에 실패했습니다.");
      if (err instanceof ApiError && err.runId) {
        setFailedId(err.runId);
        setLookup(err.runId);
      }
    } finally {
      busy.current = false;
      setLoading(false);
    }
  }
  return (
    <div className="min-h-screen">
      <header className="border-b bg-card">
        <div className="max-w-6xl mx-auto px-4 py-5">
          <h1 className="text-xl font-bold">영어 글쓰기 생성·평가</h1>
          <p className="hint mt-1">K–12 학년별 루브릭 · 포트폴리오 실행 환경</p>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        <div className="panel" role="status">
          {runtime === "mock" ? (
            <>
              <strong>Mock 모드</strong>
              <p className="text-sm mt-1">
                연결·실행 흐름을 확인하는 고정 응답입니다. 실제 글 생성·채점
                결과나 학습 데이터로 사용하지 않습니다.
              </p>
            </>
          ) : runtime === "live" ? (
            "실제 모델 연결 모드 · 평가 정확도는 검증되지 않았습니다."
          ) : runtime === "unknown" ? (
            "실행 모드를 확인할 수 없습니다."
          ) : (
            "실행 환경 확인 중…"
          )}
        </div>
        <div className="grid lg:grid-cols-[360px_minmax(0,1fr)] gap-6 items-start">
          <div className="panel">
            <h2 className="font-semibold mb-4">실행 설정</h2>
            <InputForm
              options={options}
              loading={loading}
              onSubmit={(request: RunRequest) =>
                void execute(() => runPipeline(request))
              }
            />
          </div>
          <div className="min-w-0 space-y-5" aria-busy={loading}>
            <form
              className="panel space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (lookup.trim()) void execute(() => loadRun(lookup.trim()));
              }}
            >
              <label className="field">
                저장된 실행 ID
                <input
                  required
                  value={lookup}
                  onChange={(e) => setLookup(e.target.value)}
                  placeholder="실행 ID로 저장된 결과 다시 열기"
                />
              </label>
              <button
                className="primary-button"
                disabled={loading || !lookup.trim()}
              >
                결과 조회
              </button>
              {recent.length > 0 && (
                <label className="field">
                  이번 세션의 실행
                  <select
                    value=""
                    disabled={loading}
                    onChange={(e) => {
                      if (e.target.value)
                        void execute(() => loadRun(e.target.value));
                    }}
                  >
                    <option value="">최근 실행 선택</option>
                    {recent.map((id) => (
                      <option key={id} value={id}>
                        {id}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </form>
            {error && (
              <div
                role="alert"
                className="panel border-red-300 text-red-800 break-words"
              >
                {error}
                {failedId && <p className="mt-2">실패한 실행 ID: {failedId}</p>}
              </div>
            )}
            {loading && (
              <div role="status" className="panel">
                요청 처리 중입니다. 완료되면 결과가 표시됩니다.
              </div>
            )}
            {!loading && result && (
              <>
                <section className="panel break-words">
                  <h2 className="font-semibold">
                    실행 결과 ·{" "}
                    {result.stage === "completed"
                      ? "완료"
                      : result.stage === "failed"
                        ? "실패"
                        : "진행 중"}
                  </h2>
                  <p className="text-sm mt-2">
                    {gradeLabel(result.grade)}{" "}
                    {result.assessed_content?.genre
                      ? GENRE_LABELS[result.assessed_content.genre]
                      : ""}{" "}
                    ·{" "}
                    {result.execution_mode === "mock"
                      ? "Mock 고정 응답"
                      : result.execution_mode === "live"
                        ? "실제 모델 응답"
                        : "실행 모드 미확인"}
                  </p>
                  <p className="hint mt-2">실행 ID: {result.run_id}</p>
                  {result.error && (
                    <p role="alert" className="text-red-800 mt-2">
                      처리 실패: {result.error.code}
                    </p>
                  )}
                </section>
                {result.essay && (
                  <EssayOutput
                    key={`essay-${result.run_id}`}
                    essay={result.essay}
                  />
                )}
                {result.assessed_content && (
                  <AssessmentResult
                    key={`assessment-${result.run_id}`}
                    result={result.assessed_content}
                  />
                )}
              </>
            )}
            {!loading && !result && !error && (
              <div className="panel text-muted-foreground py-16 text-center">
                설정을 선택하고 실행하면 글과 영역별 피드백이 여기에 표시됩니다.
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
