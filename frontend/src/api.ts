export interface Options {
  prompt: string
  extraction_passes: number
  max_workers: number
  max_char_buffer: number
  include_text: boolean
}
export interface Result {
  document: { text?: string; extractions?: { extraction_class: string; extraction_text: string; char_interval?: { start_pos: number; end_pos: number } }[] }
  jsonl: string
  html: string
  warnings: string[]
  skipped_pages: number[]
  omitted_entities: number
  text: string | null
}

export async function apiRequest<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${token}` },
    cache: 'no-store',
    credentials: 'omit',
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `Erreur HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}
