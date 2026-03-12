"use client"

import { useEffect, useState } from "react"
import { Phone, Mail, ExternalLink, Lock, Eye } from "lucide-react"

import { RevealLeadResponse } from "@/lib/api"
import { cn } from "@/lib/utils"

type Temperature = "HOT" | "WARM" | "COLD"

interface LeadCardProps {
  leadId?: string
  temperature: Temperature
  title: string
  price: string
  reason: string
  phone?: string
  email?: string
  protected?: boolean
  revealCost?: number
  link?: string
  onReveal?: (leadId: string) => Promise<RevealLeadResponse>
}

const TEMP_CONFIG: Record<Temperature, { label: string; badgeBg: string; badgeText: string; dot: string }> = {
  HOT: {
    label: "QUENTE",
    badgeBg: "bg-[color:var(--lead-hot-bg)]",
    badgeText: "text-[color:var(--lead-hot-text)]",
    dot: "bg-red-500",
  },
  WARM: {
    label: "MORNO",
    badgeBg: "bg-[color:var(--lead-warm-bg)]",
    badgeText: "text-[color:var(--lead-warm-text)]",
    dot: "bg-orange-400",
  },
  COLD: {
    label: "FRIO",
    badgeBg: "bg-[color:var(--lead-cold-bg)]",
    badgeText: "text-[color:var(--lead-cold-text)]",
    dot: "bg-blue-400",
  },
}

export function LeadCard({
  leadId,
  temperature,
  title,
  price,
  reason,
  phone,
  email,
  protected: isProtected = false,
  revealCost = 30,
  link,
  onReveal,
}: LeadCardProps) {
  const [revealed, setRevealed] = useState(!isProtected)
  const [revealing, setRevealing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [contactPhone, setContactPhone] = useState(phone)
  const [contactEmail, setContactEmail] = useState(email)
  const [contactLink, setContactLink] = useState(link)
  const config = TEMP_CONFIG[temperature]

  useEffect(() => {
    setRevealed(!isProtected)
    setContactPhone(phone)
    setContactEmail(email)
    setContactLink(link)
    setError(null)
  }, [email, isProtected, link, phone])

  const handleReveal = async () => {
    if (!isProtected) return

    if (!leadId || !onReveal) {
      setRevealed(true)
      return
    }

    setRevealing(true)
    setError(null)

    try {
      const revealedLead = await onReveal(leadId)
      setContactPhone(revealedLead.phone)
      setContactEmail(revealedLead.email)
      setContactLink(revealedLead.link)
      setRevealed(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao revelar lead.")
    } finally {
      setRevealing(false)
    }
  }

  const openExternalLink = () => {
    if (contactLink) {
      window.open(contactLink, "_blank", "noopener,noreferrer")
    }
  }

  return (
    <article className="bg-card border border-border rounded-lg p-4 flex flex-col gap-3 hover:shadow-sm transition-shadow group">
      <div className="flex items-start justify-between gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-bold tracking-wider uppercase",
            config.badgeBg,
            config.badgeText,
          )}
        >
          <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", config.dot)} />
          {config.label}
        </span>
        <span className="text-[13px] font-bold text-foreground tabular-nums">{price}</span>
      </div>

      <div>
        <h3 className="text-[14px] font-semibold text-foreground leading-snug text-pretty">{title}</h3>
      </div>

      <div className="bg-secondary rounded-md px-3 py-2">
        <p className="text-[12px] text-muted-foreground leading-relaxed">{reason}</p>
      </div>

      {isProtected && !revealed ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-3 flex flex-col gap-2">
          <div className="flex items-center gap-1.5 mb-0.5">
            <Lock className="w-3.5 h-3.5 text-red-500" />
            <span className="text-[11px] font-semibold text-red-600 uppercase tracking-wide">Contato Protegido</span>
          </div>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Phone className="w-3 h-3 text-red-300" />
              <span className="text-[12px] text-red-300 font-mono blur-[3px] select-none">***-****-****</span>
            </div>
            <div className="flex items-center gap-2">
              <Mail className="w-3 h-3 text-red-300" />
              <span className="text-[12px] text-red-300 font-mono blur-[3px] select-none">******@***.***</span>
            </div>
          </div>
          <button
            onClick={handleReveal}
            disabled={revealing}
            className="mt-1 w-full bg-red-600 hover:bg-red-700 text-white text-[12px] font-semibold py-1.5 px-3 rounded-md transition-colors flex items-center justify-center gap-1.5 disabled:opacity-70"
          >
            <Eye className="w-3.5 h-3.5" />
            {revealing ? "Revelando..." : `Revelar Contato (${revealCost} Creditos)`}
          </button>
          {error && <p className="text-[12px] text-red-600">{error}</p>}
        </div>
      ) : (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Phone className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            <span className="text-[13px] text-foreground font-medium tabular-nums">{contactPhone}</span>
          </div>
          <div className="flex items-center gap-2">
            <Mail className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            <span className="text-[13px] text-foreground">{contactEmail}</span>
          </div>
        </div>
      )}

      {(!isProtected || revealed) && (
        <div className="flex items-center gap-1.5 pt-1 border-t border-border">
          <a
            aria-label="Ligar"
            href={contactPhone ? `tel:${contactPhone}` : undefined}
            className="flex-1 flex items-center justify-center gap-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground hover:bg-secondary rounded-md py-1.5 transition-colors"
          >
            <Phone className="w-3.5 h-3.5" />
            Ligar
          </a>
          <div className="w-px h-4 bg-border" />
          <a
            aria-label="Email"
            href={contactEmail ? `mailto:${contactEmail}` : undefined}
            className="flex-1 flex items-center justify-center gap-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground hover:bg-secondary rounded-md py-1.5 transition-colors"
          >
            <Mail className="w-3.5 h-3.5" />
            Email
          </a>
          {contactLink && (
            <>
              <div className="w-px h-4 bg-border" />
              <button
                type="button"
                aria-label="Ver anuncio"
                onClick={openExternalLink}
                className="flex-1 flex items-center justify-center gap-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground hover:bg-secondary rounded-md py-1.5 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Anuncio
              </button>
            </>
          )}
        </div>
      )}
    </article>
  )
}
