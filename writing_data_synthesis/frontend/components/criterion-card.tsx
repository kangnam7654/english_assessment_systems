"use client";

import type { CriterionResult } from "@/lib/api";
import {
  BookOpen,
  LayoutList,
  SpellCheck,
  Languages,
  Ruler,
  type LucideIcon,
} from "lucide-react";

const CRITERION_ICONS: Record<string, LucideIcon> = {
  content: BookOpen,
  organization: LayoutList,
  vocabulary: Languages,
  grammar: SpellCheck,
  length: Ruler,
};

const SCORE_COLORS = [
  "#ef4444", // 0 - red
  "#f97316", // 1 - orange
  "#f59e0b", // 2 - amber
  "#eab308", // 3 - yellow
  "#22c55e", // 4 - green
  "#8b5cf6", // 5 - violet
];

interface CriterionCardProps {
  name: string;
  result: CriterionResult;
  lang: "en" | "ko";
}

export function CriterionCard({ name, result, lang }: CriterionCardProps) {
  const Icon = CRITERION_ICONS[name] ?? BookOpen;
  const color = SCORE_COLORS[Math.min(Math.max(Math.round(result.score), 0), 5)];
  const percentage = (result.score / 5) * 100;
  const comment = lang === "en" ? result.comment_english : result.comment_korean;

  return (
    <div className="bg-card rounded-xl border border-border p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: `${color}18` }}
          >
            <Icon size={16} style={{ color }} />
          </div>
          <span className="font-semibold capitalize text-sm">{name}</span>
        </div>
        <span className="text-lg font-bold" style={{ color }}>
          {result.score}<span className="text-xs text-muted-foreground font-normal">/5</span>
        </span>
      </div>

      {/* Score bar */}
      <div className="w-full h-2 bg-muted rounded-full overflow-hidden mb-3">
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{
            width: `${percentage}%`,
            backgroundColor: color,
          }}
        />
      </div>

      <p className="text-sm text-muted-foreground leading-relaxed">{comment}</p>
    </div>
  );
}
