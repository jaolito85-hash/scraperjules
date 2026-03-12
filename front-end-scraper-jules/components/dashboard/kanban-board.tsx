"use client"

import { Lead, RevealLeadResponse } from "@/lib/api"
import { cn } from "@/lib/utils"

import { LeadCard } from "./lead-card"

interface KanbanColumn {
  id: string
  label: string
  count: number
  accent: string
}

interface KanbanBoardProps {
  leads: Lead[]
  lastSearch: string
  onRevealLead: (leadId: string) => Promise<RevealLeadResponse>
}

export function KanbanBoard({ leads, lastSearch, onRevealLead }: KanbanBoardProps) {
  const columns: KanbanColumn[] = [
    { id: "new", label: "NOVO", count: leads.length, accent: "bg-blue-500" },
    { id: "contacted", label: "CONTATADO", count: 0, accent: "bg-amber-500" },
    { id: "negotiating", label: "NEGOCIANDO", count: 0, accent: "bg-orange-500" },
    { id: "closed", label: "FECHADO", count: 0, accent: "bg-green-500" },
  ]

  return (
    <section className="flex-1 min-h-0">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <div className="flex items-center gap-2">
          <div className="w-1 h-4 bg-primary rounded-full" />
          <h2 className="text-[13px] font-semibold text-muted-foreground uppercase tracking-widest">
            Seu CRM de Oportunidades
          </h2>
        </div>
        <p className="text-[12px] text-muted-foreground">
          {lastSearch ? `Resultado atual para: ${lastSearch}` : "Faça uma busca para preencher o pipeline."}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 pb-6">
        {columns.map((col) => (
          <KanbanColumn key={col.id} column={col} leads={leads} onRevealLead={onRevealLead} />
        ))}
      </div>
    </section>
  )
}

function KanbanColumn({
  column,
  leads,
  onRevealLead,
}: {
  column: KanbanColumn
  leads: Lead[]
  onRevealLead: (leadId: string) => Promise<RevealLeadResponse>
}) {
  return (
    <div
      className="rounded-lg border border-[color:var(--kanban-col-border)] bg-[color:var(--kanban-col)] flex flex-col min-h-[480px]"
      role="region"
      aria-label={`Coluna ${column.label}`}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-[color:var(--kanban-col-border)]">
        <div className="flex items-center gap-2">
          <span className={cn("w-2 h-2 rounded-full shrink-0", column.accent)} />
          <span className="text-[11px] font-bold text-muted-foreground tracking-[0.08em]">{column.label}</span>
        </div>
        {column.count > 0 && (
          <span className="text-[11px] font-semibold text-muted-foreground bg-card border border-border rounded-full w-5 h-5 flex items-center justify-center tabular-nums">
            {column.count}
          </span>
        )}
      </div>

      <div className="flex-1 p-3 flex flex-col gap-3">
        {column.id === "new" && leads.length > 0 &&
          leads.map((lead) => (
            <LeadCard
              key={lead.id}
              leadId={lead.id}
              temperature={lead.temperature}
              title={lead.title}
              price={lead.price}
              reason={lead.reason}
              phone={lead.phone}
              email={lead.email}
              link={lead.link ?? undefined}
              protected={!lead.is_revealed}
              revealCost={30}
              onReveal={onRevealLead}
            />
          ))}

        {column.id === "new" && leads.length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center py-8">
            <div className="w-8 h-8 rounded-full bg-card border border-border flex items-center justify-center">
              <svg className="w-4 h-4 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <p className="text-[12px] text-muted-foreground">Nenhum lead carregado ainda</p>
            <p className="text-[11px] text-muted-foreground/60">Use a busca acima para consultar o backend FastAPI</p>
          </div>
        )}

        {column.id !== "new" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center py-8">
            <div className="w-8 h-8 rounded-full bg-card border border-border flex items-center justify-center">
              <svg className="w-4 h-4 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <p className="text-[12px] text-muted-foreground">Nenhum lead aqui ainda</p>
            <p className="text-[11px] text-muted-foreground/60">Arraste cards para esta coluna</p>
          </div>
        )}
      </div>
    </div>
  )
}
