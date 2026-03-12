"use client"

import { Search, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useState } from "react"

import { SearchLeadsResponse, searchLeads } from "@/lib/api"

const CATEGORIES = [
  { value: "automotive", label: "Automotivo" },
  { value: "real_estate", label: "Imobiliario" },
  { value: "b2b_services", label: "Servicos B2B" },
]

interface SearchPanelProps {
  onResults: (response: SearchLeadsResponse, query: string) => void
}

export function SearchPanel({ onResults }: SearchPanelProps) {
  const [category, setCategory] = useState("automotive")
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSearch = async () => {
    const trimmedQuery = query.trim()
    if (!trimmedQuery) return

    setLoading(true)
    setError(null)

    try {
      const response = await searchLeads({
        searchTerm: trimmedQuery,
        category,
        limit: 10,
      })

      onResults(response, trimmedQuery)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro inesperado ao buscar leads.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="bg-card border border-border rounded-lg p-5">
      <div className="flex items-center gap-2 mb-4">
        <Sparkles className="w-4 h-4 text-muted-foreground" />
        <h2 className="text-[13px] font-semibold text-muted-foreground uppercase tracking-widest">
          Nova Busca
        </h2>
      </div>

      <div className="flex gap-3 items-stretch">
        <div className="relative shrink-0">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="appearance-none bg-secondary border border-border text-foreground text-[13px] font-medium pl-3 pr-8 h-10 rounded-md cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring transition-colors hover:bg-accent"
          >
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
          <svg
            className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2.5}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>

        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Ex: Honda Civic 2020 Sao Paulo..."
            className="w-full h-10 bg-secondary border border-border rounded-md pl-9 pr-4 text-[14px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring transition-colors"
          />
        </div>

        <Button
          onClick={handleSearch}
          disabled={loading}
          className="bg-primary text-primary-foreground hover:bg-primary/90 font-semibold text-[13px] px-5 h-10 shrink-0 gap-2"
        >
          {loading ? (
            <>
              <span className="w-3.5 h-3.5 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
              Buscando...
            </>
          ) : (
            <>
              <Search className="w-3.5 h-3.5" />
              Localizar Oportunidades
            </>
          )}
        </Button>
      </div>

      <p className="mt-3 text-[12px] text-muted-foreground">
        Dica: seja especifico, modelo, ano e localizacao aumentam a precisao dos resultados.
      </p>

      {error && <p className="mt-3 text-[12px] text-red-500">{error}</p>}
    </section>
  )
}
