"use client";

import { useState } from "react";
import type { AssessedContent } from "@/lib/api";
import { ScoreBadge } from "./score-badge";
import { CriterionCard } from "./criterion-card";
import { MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

interface AssessmentResultProps {
  result: AssessedContent;
}

export function AssessmentResult({ result }: AssessmentResultProps) {
  const [lang, setLang] = useState<"en" | "ko">("en");

  const criteria = Object.entries(result.per_criterion);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Overall Score */}
      <div className="bg-card rounded-xl border border-border p-6">
        <div className="flex flex-col items-center">
          <h3 className="font-semibold text-sm text-muted-foreground mb-4">
            Overall Score
          </h3>
          <ScoreBadge
            score={result.overall_score}
            level={result.level}
          />
        </div>
      </div>

      {/* Per-Criterion Cards */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm text-muted-foreground">
            Criteria Breakdown
          </h3>
          <div className="flex gap-1 p-0.5 bg-muted rounded-lg">
            <button
              onClick={() => setLang("en")}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-all",
                lang === "en"
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground"
              )}
            >
              EN
            </button>
            <button
              onClick={() => setLang("ko")}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-all",
                lang === "ko"
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground"
              )}
            >
              KO
            </button>
          </div>
        </div>
        <div className="grid gap-3 stagger-children">
          {criteria.map(([name, criterion]) => (
            <CriterionCard
              key={name}
              name={name}
              result={criterion}
              lang={lang}
            />
          ))}
        </div>
      </div>

      {/* Summary Feedback */}
      <div className="bg-card rounded-xl border border-border overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-muted/50">
          <MessageSquare size={16} className="text-primary" />
          <h3 className="font-semibold text-sm">Summary Feedback</h3>
        </div>
        <div className="p-4 space-y-3">
          <div>
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              English
            </span>
            <p className="text-sm leading-relaxed mt-1">
              {result.summary_feedback_english}
            </p>
          </div>
          <div className="border-t border-border pt-3">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Korean
            </span>
            <p className="text-sm leading-relaxed mt-1">
              {result.summary_feedback_korean}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
