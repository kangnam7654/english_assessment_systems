import { CRITERION_LABELS, type CriterionResult } from "@/lib/api";
export function CriterionCard({
  name,
  result,
  normalized,
  lang,
}: {
  name: string;
  result: CriterionResult;
  normalized: number | null;
  lang: "ko" | "en";
}) {
  return (
    <section className="bg-card rounded-xl border border-border p-4">
      <div className="flex justify-between gap-3 mb-2">
        <h3 className="font-semibold">{CRITERION_LABELS[name] ?? name}</h3>
        <span className="font-bold text-primary whitespace-nowrap">
          {result.score} / 4
        </span>
      </div>
      <p className="hint mb-3">
        표시값 {normalized === null ? "—" : normalized.toFixed(2)} / 100
      </p>
      <p className="text-sm leading-relaxed break-words">
        {lang === "ko" ? result.comment_korean : result.comment_english}
      </p>
    </section>
  );
}
