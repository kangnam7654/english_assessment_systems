import { useState } from "react";
import type { AnalysisResult } from "./api";
import { Assessment, Metric } from "./Results";

type Example = "appropriate" | "inappropriate" | "unavailable";
const examples: { value: Example; label: string }[] = [
  { value: "appropriate", label: "적절한 태도" },
  { value: "inappropriate", label: "부적절한 태도" },
  { value: "unavailable", label: "판정 불가" },
];

// View-only fixtures. No model execution, API requests, job records or localStorage.
export default function ModelPreview() {
  const [example, setExample] = useState<Example>("appropriate");
  const available = example !== "unavailable";
  const result: AnalysisResult = {
    mode: "assessment",
    source_sha256: "ui-example-not-a-real-video",
    features: {
      sampled_frames: 300,
      sample_fps: 5,
      has_valid_features: available,
      detected_frame_ratios: {
        face: available ? 0.92 : 0,
        at_least_one_hand: available ? 0.76 : 0,
        two_hands: available ? 0.54 : 0,
      },
      valid_frame_ratios: {
        face: available ? 0.9 : 0,
        Left: available ? 0.6 : 0,
        Right: available ? 0.68 : 0,
      },
      sequence_sha256: "ui-example-not-real-features",
    },
    assessment: available
      ? {
          status: "complete",
          label: example as "appropriate" | "inappropriate",
          positive_class_probability: example === "appropriate" ? 0.84 : 0.23,
          threshold: 0.5,
          purpose: "ui_preview_not_model_inference",
        }
      : { status: "unavailable", reason: "no_valid_features" },
  };
  return (
    <>
      <header className="header">
        <div className="header-inner">
          <a className="wordmark" href="/ui/">
            Presentation Attitude
          </a>
          <span className="brand-sub">발표 태도 평가</span>
          <a className="api-link" href="/ui/">
            실제 업로드 화면 ↗
          </a>
        </div>
      </header>
      <div className="preview-banner" role="note">
        <strong>UI 예시 · 실제 분석 결과 아님</strong>
        <span>
          판정과 모든 수치는 화면 확인용 가상 값입니다. 영상 업로드나 모델
          추론을 실행하지 않습니다.
        </span>
      </div>
      <main className="workbench verdict-preview">
        <section className="upload-section" aria-labelledby="preview-title">
          <h1 id="preview-title">모델 판정 결과 미리보기</h1>
          <p className="subtitle">
            판정 상태를 선택해 실제 UI 컴포넌트를 확인하세요.
          </p>
          <div className="dropzone preview-placeholder">
            <div className="drop-content">
              <svg
                width="64"
                height="64"
                viewBox="0 0 64 64"
                fill="none"
                aria-hidden="true"
              >
                <rect
                  x="5"
                  y="13"
                  width="54"
                  height="38"
                  rx="6"
                  stroke="currentColor"
                  strokeWidth="2"
                />
                <path
                  d="m27 24 13 8-13 8V24Z"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinejoin="round"
                />
              </svg>
              <h2>실제 영상이 없는 화면 예시</h2>
              <p>오른쪽 결과는 특정 사람이나 영상을 평가한 것이 아닙니다.</p>
            </div>
          </div>
          <fieldset className="example-selector">
            <legend>판정 상태 예시</legend>
            {examples.map((item) => (
              <label key={item.value}>
                <input
                  type="radio"
                  name="example"
                  value={item.value}
                  checked={example === item.value}
                  onChange={() => setExample(item.value)}
                />
                <span>{item.label}</span>
              </label>
            ))}
          </fieldset>
          <p className="helper">
            실제 서비스에서는 모델 응답에 따라 판정이 표시됩니다. 이 선택 버튼은
            예시 화면에만 있습니다.
          </p>
        </section>
        <section className="results-section" aria-labelledby="results-title">
          <div className="results-heading">
            <h2 id="results-title">분석 결과</h2>
          </div>
          <p className="status" role="status" aria-live="polite">
            {available
              ? "모델 판정 완료 · 예시"
              : "특징 부족으로 판정 불가 · 예시"}
          </p>
          <ol className="stages" aria-label="예시 분석 단계">
            {["업로드", "분석", "완료"].map((label, index) => (
              <li
                className="active"
                key={label}
                aria-current={index === 2 ? "step" : undefined}
              >
                <span className="stage-dot" />
                {label}
              </li>
            ))}
          </ol>
          <div className="metrics">
            <Metric
              label="얼굴 검출 비율"
              value={result.features.detected_frame_ratios.face}
            />
            <Metric
              label="한 손 이상 검출 비율"
              value={result.features.detected_frame_ratios.at_least_one_hand}
            />
            <Metric
              label="유효 얼굴 특징 비율"
              value={result.features.valid_frame_ratios.face}
            />
          </div>
          <div className="result-note">
            <p>300개 프레임 · 초당 5프레임 샘플링 · 가상 값</p>
            <p>검출 비율과 모델 판정은 서로 다른 정보입니다.</p>
          </div>
          <div aria-live="polite">
            <Assessment result={result} />
          </div>
        </section>
      </main>
      <footer>
        <span>UI preview · 모델 판정 화면 예시</span>
        <span>Portfolio reconstruction</span>
      </footer>
    </>
  );
}
