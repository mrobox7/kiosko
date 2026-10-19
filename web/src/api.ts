import type { Reply, SessionInfo } from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : response.statusText
    throw new ApiError(response.status, detail)
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

const post = (body?: unknown): RequestInit => ({
  method: 'POST',
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  login: (who: { name: string; phone: string; email: string }) =>
    call<SessionInfo>('/api/login', post(who)),
  session: (id: string) => call<SessionInfo>(`/api/sessions/${id}`),
  send: (id: string, text: string) =>
    call<Reply>(`/api/sessions/${id}/messages`, post({ text })),
  newChat: (id: string) => call<SessionInfo>(`/api/sessions/${id}/new`, post()),
  end: (id: string) => call<void>(`/api/sessions/${id}`, { method: 'DELETE' }),
}
