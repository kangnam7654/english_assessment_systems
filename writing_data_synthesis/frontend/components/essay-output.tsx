"use client";

import { FileText, Copy, Check } from "lucide-react";
import { useState } from "react";

interface EssayOutputProps {
  essay: string;
}

export function EssayOutput({ essay }: EssayOutputProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(essay);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const wordCount = essay.trim().split(/\s+/).filter(Boolean).length;

  return (
    <div className="bg-card rounded-xl border border-border overflow-hidden animate-fade-in">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/50">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-primary" />
          <h3 className="font-semibold text-sm">Generated Essay</h3>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">
            {wordCount} words
          </span>
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
      <div className="p-4">
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{essay}</p>
      </div>
    </div>
  );
}
