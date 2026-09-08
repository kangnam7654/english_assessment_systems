"use client";

import { cn } from "@/lib/utils";
import { PenTool, ClipboardCheck } from "lucide-react";
import type { Mode } from "@/lib/api";

interface ModeSelectorProps {
  value: Mode;
  onChange: (mode: Mode) => void;
}

export function ModeSelector({ value, onChange }: ModeSelectorProps) {
  return (
    <div className="flex gap-2 p-1 bg-muted rounded-xl">
      <button
        onClick={() => onChange("synthesis")}
        className={cn(
          "flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all",
          value === "synthesis"
            ? "bg-card text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground"
        )}
      >
        <PenTool size={16} />
        <span>Generate + Assess</span>
      </button>
      <button
        onClick={() => onChange("assessment")}
        className={cn(
          "flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all",
          value === "assessment"
            ? "bg-card text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground"
        )}
      >
        <ClipboardCheck size={16} />
        <span>Assess Only</span>
      </button>
    </div>
  );
}
