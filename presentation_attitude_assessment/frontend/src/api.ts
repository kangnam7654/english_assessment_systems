export type Job = {
  id: string;
  filename: string;
  status: "queued" | "running" | "succeeded" | "failed";
  attempt: number;
  size_bytes: number;
  attempts: {
    number: number;
    error: { code: string; message: string } | null;
  }[];
};
export type AnalysisResult = {
  mode: "features" | "assessment";
  source_sha256: string;
  features: {
    sampled_frames: number;
    sample_fps: number;
    has_valid_features: boolean;
    detected_frame_ratios: {
      face: number;
      at_least_one_hand: number;
      two_hands: number;
    };
    valid_frame_ratios: { face: number; Left: number; Right: number };
    sequence_sha256: string;
  };
  assessment:
    | null
    | { status: "unavailable"; reason: string }
    | {
        status: "complete";
        label: "appropriate" | "inappropriate";
        positive_class_probability: number;
        threshold: number;
        purpose: string;
      };
};
export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}
function message(status: number) {
  if (status === 413)
    return "업로드 용량을 초과했어요. 더 작은 영상을 선택해 주세요.";
  if (status === 415) return "지원하지 않는 영상 형식이에요.";
  if (status === 404)
    return "이 작업을 찾을 수 없어요. 저장소가 변경되었는지 확인해 주세요.";
  if (status === 409)
    return "작업 상태가 변경되었어요. 상태를 다시 확인해 주세요.";
  return "요청을 처리하지 못했어요. API 연결과 입력을 확인해 주세요.";
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    signal: options.signal
      ? AbortSignal.any([options.signal, AbortSignal.timeout(10000)])
      : AbortSignal.timeout(10000),
  });
  if (!response.ok)
    throw new ApiError(message(response.status), response.status);
  return response.json() as Promise<T>;
}
export function upload(
  file: File,
  progress: (percent: number | null) => void,
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/jobs?mode=features");
    xhr.timeout = 120000;
    xhr.upload.onprogress = (e) =>
      progress(
        e.lengthComputable ? Math.round((e.loaded / e.total) * 100) : null,
      );
    const uncertain = () =>
      reject(
        new ApiError(
          "업로드 응답을 받지 못했어요. 접수되었을 수 있으므로 자동 재전송하지 않습니다. API 연결을 확인해 주세요.",
        ),
      );
    xhr.onerror = uncertain;
    xhr.ontimeout = uncertain;
    xhr.onload = () => {
      if (xhr.status !== 202) {
        reject(new ApiError(message(xhr.status), xhr.status));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as Job);
      } catch {
        uncertain();
      }
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
