import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { useAnalysis } from "./useAnalysis";
import { Assessment, Metric } from "./Results";

function UploadIcon() {
  return (
    <svg
      width="64"
      height="64"
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M32 43V5m0 0L16 21M32 5l16 16M6 45v10a4 4 0 0 0 4 4h44a4 4 0 0 0 4-4V45"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
export default function App() {
  const analysis = useAnalysis();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [fileError, setFileError] = useState("");
  const [previewError, setPreviewError] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [maxBytes, setMaxBytes] = useState(256 * 1024 * 1024);
  const [apiError, setApiError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    request<{ max_upload_bytes: number }>("/health", {
      signal: controller.signal,
    })
      .then((health) => setMaxBytes(health.max_upload_bytes))
      .catch(() => {
        if (!controller.signal.aborted)
          setApiError(
            "API에 연결하지 못했어요. 서버가 실행 중인지 확인해 주세요.",
          );
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    setPreviewError(false);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  function select(next?: File) {
    if (!next || analysis.busy) return;
    if (!/\.(mp4|m4v|mov|mkv|webm|avi)$/i.test(next.name)) {
      setFileError("MP4, MOV, M4V, MKV, WebM, AVI 영상을 선택해 주세요.");
      return;
    }
    if (!next.size || next.size > maxBytes) {
      setFileError(
        `비어 있지 않은 ${Math.round(maxBytes / 1024 / 1024)} MiB 이하 영상을 선택해 주세요.`,
      );
      return;
    }
    analysis.reset();
    setFileError("");
    setFile(next);
  }
  function clear() {
    if (analysis.busy) return;
    analysis.reset();
    setFile(null);
    setFileError("");
    if (input.current) input.current.value = "";
  }
  const { job, result, sending, busy } = analysis;
  const status = sending
    ? analysis.progress === null
      ? "재시도 요청 중"
      : `영상 업로드 중 · ${analysis.progress}%`
    : analysis.restoring
      ? "이전 작업 확인 중"
      : job?.status === "queued"
        ? "분석 대기 중"
        : job?.status === "running"
          ? "영상 분석 중"
          : job?.status === "failed"
            ? "분석 실패"
            : result
              ? "특징 추출 완료"
              : job?.status === "succeeded"
                ? "결과 불러오는 중"
                : file
                  ? "분석할 준비가 되었어요"
                  : "영상 업로드 대기";
  const stage = result ? 2 : job && job.status !== "failed" ? 1 : 0;
  function download() {
    if (!result) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `analysis-${job?.id ?? "result"}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      <header className="header">
        <div className="header-inner">
          <a className="wordmark" href="/ui/">
            Presentation Attitude
          </a>
          <span className="brand-sub">발표 태도 평가</span>
          <a className="api-link" href="/docs" target="_blank" rel="noreferrer">
            API 문서 ↗
          </a>
        </div>
      </header>
      <main className="workbench">
        <section className="upload-section" aria-labelledby="title">
          <h1 id="title">발표 영상을 분석해 보세요</h1>
          <p className="subtitle">영상 속 얼굴과 손의 움직임을 확인합니다.</p>
          <input
            ref={input}
            className="sr-only"
            type="file"
            tabIndex={-1}
            aria-label="발표 영상 선택"
            accept=".mp4,.mov,.m4v,.mkv,.webm,.avi"
            disabled={busy}
            onChange={(e) => {
              select(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <div
            className={`dropzone ${dragging ? "dragging" : ""} ${preview ? "has-video" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              select(e.dataTransfer.files[0]);
            }}
          >
            {preview ? (
              <>
                <video
                  controls
                  playsInline
                  src={preview}
                  onError={() => setPreviewError(true)}
                  onLoadedData={(e) =>
                    setPreviewError(e.currentTarget.videoWidth === 0)
                  }
                  aria-label="선택한 발표 영상 미리보기"
                />
                {previewError ? (
                  <p className="preview-error">
                    이 브라우저에서 미리보기를 재생할 수 없어요. 서버의 영상
                    분석은 시도할 수 있습니다.
                  </p>
                ) : null}
              </>
            ) : job ? (
              <div className="drop-content">
                <UploadIcon />
                <h2>{job.filename}</h2>
                <p>이전 작업의 상태와 결과를 불러왔어요.</p>
                <p className="formats">
                  새로고침 후에는 원본 미리보기가 보관되지 않습니다.
                </p>
              </div>
            ) : (
              <div className="drop-content">
                <UploadIcon />
                <h2>영상을 여기에 놓아주세요</h2>
                <p>또는 파일을 선택해 업로드하세요</p>
                <button
                  className="outline"
                  onClick={() => input.current?.click()}
                  disabled={busy}
                >
                  영상 선택
                </button>
                <p className="formats">
                  MP4 · MOV · WebM · 최대 {Math.round(maxBytes / 1024 / 1024)}{" "}
                  MiB
                </p>
              </div>
            )}
          </div>
          <div className="file-line">
            <p>
              {file
                ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MiB`
                : "얼굴과 손이 보이는 발표 영상이 분석에 적합합니다."}
            </p>
            {file || job ? (
              <button className="text-button" disabled={busy} onClick={clear}>
                새 영상 선택
              </button>
            ) : null}
          </div>
          {fileError ? (
            <p className="error" role="alert">
              {fileError}
            </p>
          ) : null}
          {apiError && !job ? (
            <p className="error" role="alert">
              {apiError}
            </p>
          ) : null}
          <button
            className="primary"
            disabled={!file || Boolean(fileError) || busy || Boolean(job)}
            onClick={() => {
              if (file) {
                setApiError("");
                void analysis.start(file);
              }
            }}
          >
            {sending
              ? status
              : job?.status === "running"
                ? "영상 분석 중…"
                : job?.status === "queued"
                  ? "분석 대기 중…"
                  : job?.status === "failed"
                    ? "분석 실패"
                    : result
                      ? "분석 완료"
                      : "분석 시작"}
          </button>
          {sending && analysis.progress !== null ? (
            <p className="helper" aria-live="polite">
              파일 전송 {analysis.progress}% · 영상 분석 진행률과는 다릅니다.
            </p>
          ) : null}
          {analysis.error ? (
            <div className="error" role="alert">
              <p>{analysis.error}</p>
              {job ? (
                <button className="text-button" onClick={analysis.reconnect}>
                  상태 다시 확인
                </button>
              ) : null}
            </div>
          ) : null}
          {job ? (
            <p className="job-id">
              작업 ID <code>{job.id}</code> · 실행 {job.attempt}회
            </p>
          ) : null}
        </section>
        <section className="results-section" aria-labelledby="results-title">
          <div className="results-heading">
            <h2 id="results-title">분석 결과</h2>
            {result ? (
              <button className="text-button" onClick={download}>
                JSON 저장 ↓
              </button>
            ) : null}
          </div>
          <p className="status" role="status" aria-live="polite">
            {status}
          </p>
          <ol className="stages" aria-label="분석 단계">
            {["업로드", "분석", "완료"].map((label, index) => (
              <li
                key={label}
                className={index <= stage ? "active" : ""}
                aria-current={index === stage ? "step" : undefined}
              >
                <span
                  className={`stage-dot ${index === stage && busy ? "pulse" : ""}`}
                />
                {label}
              </li>
            ))}
          </ol>
          {job?.status === "queued" ? (
            <p className="helper">
              작업이 접수되었어요. 워커가 실행되면 순서대로 분석합니다. 현재
              워커의 연결 여부는 확인하지 않습니다.
            </p>
          ) : null}
          {job?.status === "running" ? (
            <p className="helper">
              영상 전체에서 특징을 추출하고 있어요. 현재 단계별 진행률과 남은
              시간은 제공하지 않습니다.
            </p>
          ) : null}
          {job?.status === "failed" ? (
            <div className="failure" role="alert">
              <h3>영상을 분석하지 못했어요</h3>
              <p>
                {job.attempts.at(-1)?.error?.code === "worker_interrupted"
                  ? "분석 워커가 중단되었어요. 워커를 다시 실행한 뒤 재시도해 주세요."
                  : "영상 형식 또는 분석 중 오류가 발생했어요. 워커 로그를 확인한 뒤 재시도할 수 있습니다."}
              </p>
              <button
                className="outline"
                onClick={() => void analysis.retry()}
                disabled={sending}
              >
                분석 재시도
              </button>
            </div>
          ) : null}
          <div className="metrics">
            <Metric
              label="얼굴 검출 비율"
              value={result?.features.detected_frame_ratios.face}
            />
            <Metric
              label="한 손 이상 검출 비율"
              value={result?.features.detected_frame_ratios.at_least_one_hand}
            />
            <Metric
              label="유효 얼굴 특징 비율"
              value={result?.features.valid_frame_ratios.face}
            />
          </div>
          {result ? (
            <div className="result-note">
              <p>
                {result.features.sampled_frames.toLocaleString()}개 프레임 ·
                초당 {result.features.sample_fps}프레임 샘플링
              </p>
              <p>
                {result.features.has_valid_features
                  ? "비율은 전체 샘플 프레임 기준입니다. 검출 비율은 태도 점수가 아닙니다."
                  : "사용 가능한 특징이 없습니다. 얼굴과 손이 보이는 영상을 확인해 주세요."}
              </p>
            </div>
          ) : null}
          <Assessment result={result} />
        </section>
      </main>
      <footer>
        <span>전체 영상 기준 · 얼굴과 손 랜드마크</span>
        <span>Portfolio reconstruction</span>
      </footer>
    </>
  );
}
