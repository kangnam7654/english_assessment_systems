import { useEffect, useState } from "react";
import {
  ApiError,
  request,
  upload,
  type Job,
  type AnalysisResult,
} from "./api";

const storageKey = "presentation-attitude:last-job:v1";
function savedJob() {
  try {
    const id = localStorage.getItem(storageKey);
    return id && /^[a-f0-9]{32}$/.test(id) ? id : null;
  } catch {
    return null;
  }
}
function remember(id: string | null) {
  try {
    if (id) localStorage.setItem(storageKey, id);
    else localStorage.removeItem(storageKey);
  } catch {
    /* Storage can be unavailable in private browsers. */
  }
}
export function useAnalysis() {
  const [jobId, setJobId] = useState(savedJob);
  const [job, setJob] = useState<Job | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const current = await request<Job>(`/jobs/${jobId}`, {
          signal: controller.signal,
        });
        if (cancelled) return;
        setJob(current);
        setError("");
        if (current.status === "succeeded") {
          const completed = await request<AnalysisResult>(
            `/jobs/${jobId}/result`,
            { signal: controller.signal },
          );
          if (!cancelled) setResult(completed);
          return;
        }
        if (current.status === "failed") return;
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          setError(e.message);
          remember(null);
          setJobId(null);
          setJob(null);
          setResult(null);
          return;
        }
        setError(
          "상태 조회 연결이 끊겼어요. 마지막 상태를 유지하며 다시 확인하고 있습니다.",
        );
      }
      if (!cancelled) timer = setTimeout(poll, 2000);
    }
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [jobId, refresh]);

  const accept = (next: Job) => {
    setJob(next);
    setJobId(next.id);
    remember(next.id);
    setResult(null);
    setError("");
    setRefresh((v) => v + 1);
  };
  async function start(file: File) {
    if (sending) return;
    setSending(true);
    setError("");
    setProgress(0);
    try {
      accept(await upload(file, setProgress));
    } catch (e) {
      setError(e instanceof Error ? e.message : "업로드에 실패했어요.");
    } finally {
      setSending(false);
      setProgress(null);
    }
  }
  async function retry() {
    if (!job || sending) return;
    setSending(true);
    setError("");
    try {
      accept(await request<Job>(`/jobs/${job.id}/retry`, { method: "POST" }));
    } catch {
      setError("재시도 응답을 확인하지 못했어요. 작업 상태를 다시 조회합니다.");
      setRefresh((v) => v + 1);
    } finally {
      setSending(false);
    }
  }
  function reset() {
    remember(null);
    setJobId(null);
    setJob(null);
    setResult(null);
    setError("");
  }
  const busy =
    sending ||
    Boolean(
      jobId && (!job || job.status === "queued" || job.status === "running"),
    );
  return {
    job,
    result,
    error,
    sending,
    progress,
    busy,
    restoring: Boolean(jobId && !job),
    start,
    retry,
    reset,
    reconnect: () => setRefresh((v) => v + 1),
  };
}
