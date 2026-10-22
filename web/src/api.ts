import type { LineRequest, Menu, Reply, SessionInfo } from './types'

export class ApiError extends Error {
  status: number
  code: string | undefined // set when the server says why a tap was refused

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'content-type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    // A refused tap carries { code, message, hint }; other errors carry a plain sentence.
    const detail = body?.detail
    const message =
      typeof detail === 'string' ? detail : typeof detail?.message === 'string' ? detail.message : response.statusText
    throw new ApiError(response.status, message, typeof detail?.code === 'string' ? detail.code : undefined)
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

const send = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  /** The menu to browse: sections, dishes, pictures, choices. */
  menu: () => call<Menu>('/api/menu'),
  /** The next customer at the lane: a fresh chat with an empty order. */
  start: () => call<SessionInfo>('/api/sessions', send('POST')),
  session: (id: string) => call<SessionInfo>(`/api/sessions/${id}`),
  /** The customer is still there (browsing), so the server does not end the order as idle. */
  keepAlive: (id: string) => call<void>(`/api/sessions/${id}/keepalive`, send('POST')),
  /** The customer left: the server cancels the draft order and forgets the chat. */
  end: (id: string) => call<void>(`/api/sessions/${id}`, send('DELETE')),
  send: (id: string, text: string) => call<Reply>(`/api/sessions/${id}/messages`, send('POST', { text })),
  // Taps on the cart. Each answers with the session as it now is.
  addLine: (id: string, line: LineRequest) => call<SessionInfo>(`/api/sessions/${id}/lines`, send('POST', line)),
  setQuantity: (id: string, line: number, quantity: number) =>
    call<SessionInfo>(`/api/sessions/${id}/lines/${line}`, send('PATCH', { quantity })),
  removeLine: (id: string, line: number) => call<SessionInfo>(`/api/sessions/${id}/lines/${line}`, send('DELETE')),
  place: (id: string) => call<SessionInfo>(`/api/sessions/${id}/place`, send('POST')),
}
