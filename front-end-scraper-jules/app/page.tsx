"use client"

import { startTransition, useState } from "react"

import { Header } from "@/components/dashboard/header"
import { SearchPanel } from "@/components/dashboard/search-panel"
import { StatsBar } from "@/components/dashboard/stats-bar"
import { KanbanBoard } from "@/components/dashboard/kanban-board"
import { Lead, RevealLeadResponse, SearchLeadsResponse, revealLead } from "@/lib/api"

export default function DashboardPage() {
  const [leads, setLeads] = useState<Lead[]>([])
  const [lastSearch, setLastSearch] = useState("")
  const [creditsRemaining, setCreditsRemaining] = useState<number | null>(null)

  const handleSearchResults = (response: SearchLeadsResponse, query: string) => {
    startTransition(() => {
      setLeads(response.leads)
      setLastSearch(query)
      setCreditsRemaining(response.credits_remaining)
    })
  }

  const handleRevealLead = async (leadId: string): Promise<RevealLeadResponse> => {
    const revealedLead = await revealLead(leadId)

    setCreditsRemaining(revealedLead.credits_remaining)
    setLeads((current) =>
      current.map((lead) =>
        lead.id === leadId
          ? {
              ...lead,
              is_revealed: true,
              phone: revealedLead.phone,
              email: revealedLead.email,
              seller_name: revealedLead.seller_name,
              link: revealedLead.link,
            }
          : lead,
      ),
    )

    return revealedLead
  }

  return (
    <div className="min-h-screen bg-background flex flex-col font-sans">
      <Header />

      <main className="flex-1 flex flex-col gap-5 px-6 py-5 max-w-[1600px] w-full mx-auto">
        <StatsBar leads={leads} creditsRemaining={creditsRemaining} />
        <SearchPanel onResults={handleSearchResults} />
        <KanbanBoard leads={leads} lastSearch={lastSearch} onRevealLead={handleRevealLead} />
      </main>
    </div>
  )
}
