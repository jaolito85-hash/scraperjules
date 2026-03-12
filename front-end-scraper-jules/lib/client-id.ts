const STORAGE_KEY = "arbitragem-client-id"

function generateFallbackId(): string {
  const timestamp = Date.now().toString(36)
  const random = Math.random().toString(36).slice(2, 10)
  return `client-${timestamp}-${random}`
}

export function generateClientSafeId(): string {
  if (typeof globalThis !== "undefined" && globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID()
  }

  return generateFallbackId()
}

export function getClientId(): string {
  if (typeof window === "undefined") {
    return "server-render"
  }

  const existingClientId = window.localStorage.getItem(STORAGE_KEY)
  if (existingClientId) {
    return existingClientId
  }

  const nextClientId = generateClientSafeId()
  window.localStorage.setItem(STORAGE_KEY, nextClientId)
  return nextClientId
}
