const STORAGE_KEY = "arbitragem-client-id"

export function getClientId(): string {
  if (typeof window === "undefined") {
    return "server-render"
  }

  const existingClientId = window.localStorage.getItem(STORAGE_KEY)
  if (existingClientId) {
    return existingClientId
  }

  const nextClientId = window.crypto.randomUUID()
  window.localStorage.setItem(STORAGE_KEY, nextClientId)
  return nextClientId
}
