import { useCallback, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import type { LineRequest, SessionInfo } from '../types'

export const TIMED_OUT = 'That order timed out and was cancelled. Touch to start a new one.'
export const KEEPALIVE_MS = 30_000

const describe = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong')

/** The customer's order: starting it, the taps that change it, and ending it. No session means
 * nobody is ordering, which is when the welcome screen shows. */
export function useOrder(onStart: () => void) {
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [pending, setPending] = useState(false) // a tap is on its way to the server
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('') // why the welcome screen is back, if not by choice
  const current = useRef<string | null>(null)
  const lastPing = useRef(0)

  /** The customer is done or gone: cancel the draft on the server and show the welcome screen. */
  const leave = useCallback((why = '') => {
    const id = current.current
    current.current = null
    setSession(null)
    setNotice(why)
    setError('')
    if (id) api.end(id).catch(() => undefined)
  }, [])

  const start = useCallback(async () => {
    if (current.current) return
    setStarting(true)
    setError('')
    setNotice('')
    try {
      onStart()
      const fresh = await api.start()
      current.current = fresh.session_id
      setSession(fresh)
    } catch (e) {
      setError(describe(e))
    } finally {
      setStarting(false)
    }
  }, [onStart])

  /** Send one tap or read the session; the answer is the session as it now is. A 404 means the
   * server already ended this order for being idle. */
  const run = useCallback(
    async (job: (id: string) => Promise<SessionInfo>, quiet = false) => {
      const id = current.current
      if (!id) return false
      if (!quiet) setPending(true)
      setError('')
      try {
        const next = await job(id)
        if (current.current === id) setSession(next)
        return true
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) leave(TIMED_OUT)
        else setError(describe(e))
        return false
      } finally {
        if (!quiet) setPending(false)
      }
    },
    [leave],
  )

  /** Tell the server the customer is still there, at most every 30 seconds. */
  const keepAlive = useCallback(() => {
    const id = current.current
    if (!id || Date.now() - lastPing.current < KEEPALIVE_MS) return
    lastPing.current = Date.now()
    api.keepAlive(id).catch((e: unknown) => {
      if (e instanceof ApiError && e.status === 404) leave(TIMED_OUT)
    })
  }, [leave])

  return {
    session,
    pending,
    starting,
    error,
    notice,
    dismissError: () => setError(''),
    start,
    leave,
    keepAlive,
    refresh: () => run((id) => api.session(id), true),
    addLine: (line: LineRequest) => run((id) => api.addLine(id, line)),
    setQuantity: (line: number, quantity: number) => run((id) => api.setQuantity(id, line, quantity)),
    removeLine: (line: number) => run((id) => api.removeLine(id, line)),
    place: () => run((id) => api.place(id)),
  }
}
