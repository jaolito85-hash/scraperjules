"use client"

import { Download, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"

export function Header() {
  return (
    <header className="bg-card border-b border-border h-14 flex items-center px-6 shrink-0">
      <div className="flex items-center gap-2 flex-1">
        {/* Logo mark */}
        <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center shrink-0">
          <Zap className="w-4 h-4 text-primary-foreground fill-current" />
        </div>
        <span className="font-semibold text-foreground tracking-tight text-[15px]">
          Arbitragem <span className="text-muted-foreground font-normal">AI</span>
        </span>
      </div>

      <div className="flex items-center gap-2">
        {/* Credits badge */}
        <button className="inline-flex items-center gap-1.5 bg-secondary border border-border text-foreground text-[13px] font-medium px-3 py-1.5 rounded-md hover:bg-accent transition-colors">
          <Zap className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
          <span>970 Créditos</span>
        </button>

        {/* Download CSV */}
        <Button
          variant="outline"
          size="sm"
          className="text-[13px] font-medium gap-1.5 h-8"
        >
          <Download className="w-3.5 h-3.5" />
          Download CSV
        </Button>
      </div>
    </header>
  )
}
