import { generateClientSafeId, getClientId } from "@/lib/client-id"

export type LeadTemperature = "HOT" | "WARM" | "COLD"

export interface Lead {
  id: string
  title: string
  price: string
  temperature: LeadTemperature
  reason: string
  is_revealed: boolean
  phone: string
  email: string
  seller_name: string
  link?: string | null
}

export interface SearchLeadsPayload {
  searchTerm: string
  category: string
  limit?: number
}

export interface SearchLeadsResponse {
  message: string
  credits_remaining: number
  leads: Lead[]
}

export interface RevealLeadResponse {
  message: string
  phone: string
  email: string
  seller_name: string
  link: string
  credits_remaining: number
  already_revealed: boolean
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

function normalizeTemperature(value: string): LeadTemperature {
  const normalized = value?.toUpperCase?.() ?? "COLD"

  if (normalized === "QUENTE") return "HOT"
  if (normalized === "MORNO") return "WARM"
  if (normalized === "FRIO") return "COLD"
  if (normalized === "HOT" || normalized === "WARM" || normalized === "COLD") return normalized

  return "COLD"
}

function normalizeLead(lead: Partial<Lead>): Lead {
  return {
    id: String(lead.id ?? generateClientSafeId()),
    title: lead.title ?? "Lead sem titulo",
    price: lead.price ?? "R$ 0",
    temperature: normalizeTemperature(String(lead.temperature ?? "COLD")),
    reason: lead.reason ?? "Sem justificativa retornada pela API.",
    is_revealed: Boolean(lead.is_revealed),
    phone: lead.phone ?? "",
    email: lead.email ?? "",
    seller_name: lead.seller_name ?? "Oculto",
    link: lead.link ?? null,
  }
}

function buildHeaders() {
  return {
    "Content-Type": "application/json",
    "X-User-Id": getClientId(),
  }
}

export async function searchLeads({ searchTerm, category, limit = 10 }: SearchLeadsPayload): Promise<SearchLeadsResponse> {
  const response = await fetch(`${API_URL}/leads/search`, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify({
      search_term: searchTerm,
      category,
      limit,
    }),
    cache: "no-store",
  })

  if (!response.ok) {
    throw new Error("Nao foi possivel buscar leads no backend.")
  }

  const data = (await response.json()) as { message?: string; credits_remaining?: number; leads?: Partial<Lead>[] }

  return {
    message: data.message ?? "Busca concluida.",
    credits_remaining: data.credits_remaining ?? 0,
    leads: (data.leads ?? []).map(normalizeLead),
  }
}

export async function revealLead(leadId: string): Promise<RevealLeadResponse> {
  const response = await fetch(`${API_URL}/leads/${leadId}/reveal`, {
    method: "POST",
    headers: {
      "X-User-Id": getClientId(),
    },
    cache: "no-store",
  })

  if (!response.ok) {
    const errorData = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(errorData?.detail ?? "Nao foi possivel revelar este lead.")
  }

  return (await response.json()) as RevealLeadResponse
}
