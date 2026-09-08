import type { AnalysisResult } from "./api";

export function Metric({ label, value }: { label: string; value?: number }) {
  const percent =
    value === undefined ? null : Math.min(100, Math.max(0, value * 100));
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{percent === null ? "—" : `${percent.toFixed(1)}%`}</strong>
      <div className="meter" aria-hidden="true">
        <div style={{ width: `${percent ?? 0}%` }} />
      </div>
    </div>
  );
}
export function Assessment({ result }: { result: AnalysisResult | null }) {
  const assessment = result?.assessment;
  let heading = "태도 판정 준비 중";
  let text =
    "현재는 특징 추출 결과를 확인할 수 있어요. 실제 태도 분류 모델은 아직 준비되지 않았습니다.";
  if (assessment?.status === "unavailable") {
    heading = "태도 판정 불가";
    text =
      "사용 가능한 특징이 없어 판정하지 않았어요. 얼굴과 손이 보이는 영상을 사용해 주세요.";
  } else if (assessment?.status === "complete") {
    heading =
      assessment.label === "appropriate"
        ? "모델 판정: 적절한 태도"
        : "모델 판정: 부적절한 태도";
    text = `적절한 태도의 모델 출력 확률 ${(assessment.positive_class_probability * 100).toFixed(1)}% · 임계값 ${assessment.threshold}. 검증된 신뢰도나 보정된 확률을 의미하지 않습니다.`;
  }
  return (
    <div className="assessment">
      <span className="info-icon" aria-hidden="true">
        i
      </span>
      <div>
        <h3>{heading}</h3>
        <p>{text}</p>
      </div>
    </div>
  );
}
