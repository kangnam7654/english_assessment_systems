"use client";
import { useState } from "react";
import {
  GENRE_LABELS,
  LEVEL_LABELS,
  gradeLabel,
  type Grade,
  type Genre,
  type Level,
  type Mode,
  type RubricOption,
  type RunRequest,
} from "@/lib/api";

export function InputForm({
  options,
  loading,
  onSubmit,
}: {
  options: RubricOption[];
  loading: boolean;
  onSubmit: (request: RunRequest) => void;
}) {
  const [mode, setMode] = useState<Mode>("synthesis");
  const [grade, setGrade] = useState<Grade>("us_6");
  const [genre, setGenre] = useState<Genre>("argumentative");
  const [level, setLevel] = useState<Level>("intermediate");
  const [task, setTask] = useState("");
  const [essay, setEssay] = useState("");
  const [sources, setSources] = useState<string[]>([""]);
  const grades = [...new Set(options.map((o) => o.grade))];
  const genres = options.filter((o) => o.grade === grade);
  const selected = genres.find((o) => o.genre === genre);
  const example = () => {
    setTask(
      genre === "narrative"
        ? "Tell a story about a child finding a seed at school."
        : "Should the school create a garden? Explain your answer using the passage.",
    );
    if (genre === "informative")
      setTask("Explain how a school garden works, using the supplied passage.");
    setSources(
      genre === "narrative"
        ? [""]
        : [
            "Fictional practice passage: A school garden lets children observe plants. It needs regular watering, including during holidays.",
          ],
    );
    setEssay(
      "A school garden helps children learn about plants. Students can take turns watering it. The school needs a plan to care for it during holidays.",
    );
  };
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (
          !selected ||
          !task.trim() ||
          (mode === "assessment" && !essay.trim())
        )
          return;
        const passages = sources
          .filter((s) => s.trim())
          .map((text, i) => ({
            source_id: `source-${i + 1}`,
            text: text.trim(),
          }));
        if (selected.requires_sources && !passages.length) return;
        onSubmit({
          mode,
          grade_for_student: grade,
          grade_for_assessor: grade,
          genre,
          rubric_id: "project-writing-v1",
          level,
          user_prompt: task.trim(),
          ...(mode === "assessment" ? { essay: essay.trim() } : {}),
          source_passages: passages,
        });
      }}
    >
      <fieldset
        disabled={loading || !options.length}
        className="space-y-4 disabled:opacity-60"
      >
        <label className="field">
          실행 방식
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as Mode)}
          >
            <option value="synthesis">글 생성 후 평가</option>
            <option value="assessment">내 글 평가</option>
          </select>
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="field">
            학년
            <select
              value={grade}
              onChange={(e) => {
                const next = e.target.value as Grade;
                setGrade(next);
                if (!options.some((o) => o.grade === next && o.genre === genre))
                  setGenre(options.find((o) => o.grade === next)!.genre);
              }}
            >
              {grades.map((g) => (
                <option key={g} value={g}>
                  {gradeLabel(g)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            글 유형
            <select
              value={genre}
              onChange={(e) => setGenre(e.target.value as Genre)}
            >
              {genres.map((o) => (
                <option key={o.genre} value={o.genre}>
                  {GENRE_LABELS[o.genre]}
                </option>
              ))}
            </select>
          </label>
        </div>
        {mode === "synthesis" && (
          <label className="field">
            생성 목표 수준
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value as Level)}
            >
              {Object.entries(LEVEL_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <span className="hint">
              검수자에게는 목표 수준을 전달하지 않습니다.
            </span>
          </label>
        )}
        <button
          type="button"
          onClick={example}
          className="text-sm text-primary underline underline-offset-4"
        >
          가상 예시 채우기
        </button>
        <label className="field">
          과제 / 작성 지시
          <textarea
            required
            value={task}
            onChange={(e) => setTask(e.target.value)}
            rows={3}
            placeholder="영어로 작성할 과제와 조건을 입력하세요."
          />
        </label>
        {mode === "assessment" && (
          <label className="field">
            평가할 영어 글
            <textarea
              required
              value={essay}
              onChange={(e) => setEssay(e.target.value)}
              rows={6}
              placeholder="평가할 글을 붙여 넣으세요."
            />
          </label>
        )}
        <div className="space-y-3">
          <p className="text-sm font-medium">
            참고 지문 {selected?.requires_sources ? "(필수)" : "(선택)"}
          </p>
          <p className="hint">
            {genre === "narrative"
              ? "서사문에는 출처 사용 점수를 매기지 않습니다."
              : "입력한 지문을 기준으로 내용과 출처 사용을 검수합니다."}
          </p>
          {sources.map((source, i) => (
            <div key={i} className="space-y-1">
              <label className="field">
                지문 {i + 1}
                <textarea
                  required={
                    selected?.requires_sources &&
                    i === 0 &&
                    !sources.some((s) => s.trim())
                  }
                  value={source}
                  rows={3}
                  onChange={(e) =>
                    setSources(
                      sources.map((s, n) => (n === i ? e.target.value : s)),
                    )
                  }
                />
              </label>
              {i > 0 && (
                <button
                  type="button"
                  className="hint underline"
                  onClick={() => setSources(sources.filter((_, n) => n !== i))}
                >
                  지문 {i + 1} 삭제
                </button>
              )}
            </div>
          ))}
          <button
            type="button"
            className="text-sm text-primary"
            onClick={() => setSources([...sources, ""])}
          >
            + 지문 추가
          </button>
        </div>
        <button
          className="primary-button w-full"
          type="submit"
          disabled={
            !selected ||
            !task.trim() ||
            (mode === "assessment" && !essay.trim()) ||
            (selected?.requires_sources && !sources.some((s) => s.trim()))
          }
        >
          {loading
            ? "실행 중…"
            : mode === "synthesis"
              ? "생성·평가 실행"
              : "내 글 평가 실행"}
        </button>
      </fieldset>
    </form>
  );
}
