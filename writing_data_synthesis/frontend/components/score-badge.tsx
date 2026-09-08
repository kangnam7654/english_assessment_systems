"use client";

import { LEVEL_COLORS, type Level } from "@/lib/api";

interface ScoreBadgeProps {
  score: number;
  level: Level;
  size?: number;
}

export function ScoreBadge({ score, level, size = 140 }: ScoreBadgeProps) {
  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = LEVEL_COLORS[level];

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: size, height: size }}>
        <svg
          viewBox="0 0 100 100"
          className="w-full h-full -rotate-90"
        >
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke="var(--border)"
            strokeWidth="8"
          />
          <circle
            cx="50"
            cy="50"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="animate-score"
            style={{ "--score-offset": offset } as React.CSSProperties}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold" style={{ color }}>
            {Math.round(score)}
          </span>
          <span className="text-xs text-muted-foreground">/100</span>
        </div>
      </div>
      <span
        className="px-3 py-1 rounded-full text-sm font-semibold text-white capitalize"
        style={{ backgroundColor: color }}
      >
        {level}
      </span>
    </div>
  );
}
