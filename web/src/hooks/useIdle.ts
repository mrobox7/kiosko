import { useCallback, useEffect, useRef, useState } from 'react'

const TOUCHES = ['pointerdown', 'keydown', 'wheel'] as const

/** Calls `onIdle` once `ms` pass with no touch or key press anywhere on the page. `onActive` runs
 * on every touch, so the caller can tell the server the customer is still there. `poke` counts as a
 * touch, for activity that is not one, such as a spoken reply. */
export function useIdle({
  enabled,
  ms,
  onIdle,
  onActive,
}: {
  enabled: boolean
  ms: number
  onIdle: () => void
  onActive?: () => void
}) {
  const latest = useRef({ onIdle, onActive })
  const [pokes, setPokes] = useState(0)

  useEffect(() => {
    latest.current = { onIdle, onActive }
  })

  useEffect(() => {
    if (!enabled) return
    let timer = 0
    const restart = () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(() => latest.current.onIdle(), ms)
    }
    const touched = () => {
      restart()
      latest.current.onActive?.()
    }
    restart()
    for (const name of TOUCHES) window.addEventListener(name, touched, { passive: true })
    return () => {
      window.clearTimeout(timer)
      for (const name of TOUCHES) window.removeEventListener(name, touched)
    }
  }, [enabled, ms, pokes])

  return useCallback(() => setPokes((n) => n + 1), [])
}
