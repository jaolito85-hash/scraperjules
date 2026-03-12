import { TrendingUp, Coins, Target, Thermometer } from "lucide-react"

import { Lead } from "@/lib/api"

interface StatsBarProps {
  leads: Lead[]
  creditsRemaining: number | null
}

export function StatsBar({ leads, creditsRemaining }: StatsBarProps) {
  const hotLeads = leads.filter((lead) => lead.temperature === "HOT").length
  const warmLeads = leads.filter((lead) => lead.temperature === "WARM").length
  const coldLeads = leads.filter((lead) => lead.temperature === "COLD").length

  const stats = [
    { icon: Target, label: "Leads Retornados", value: String(leads.length), delta: "ultima busca" },
    { icon: Coins, label: "Creditos", value: creditsRemaining === null ? "--" : String(creditsRemaining), delta: "saldo atual" },
    { icon: TrendingUp, label: "Leads Quentes", value: String(hotLeads), delta: "alta prioridade" },
    { icon: Thermometer, label: "Mornos + Frios", value: String(warmLeads + coldLeads), delta: "follow-up" },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="bg-card border border-border rounded-lg px-4 py-3 flex items-center gap-3"
        >
          <div className="w-8 h-8 rounded-md bg-secondary flex items-center justify-center shrink-0">
            <stat.icon className="w-4 h-4 text-muted-foreground" />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] text-muted-foreground font-medium truncate">{stat.label}</p>
            <p className="text-[18px] font-bold text-foreground leading-tight tabular-nums">{stat.value}</p>
            <p className="text-[11px] text-muted-foreground/70 truncate">{stat.delta}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
