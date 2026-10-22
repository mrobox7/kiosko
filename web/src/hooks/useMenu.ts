import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { Menu } from '../types'

const describe = (e: unknown) => (e instanceof Error ? e.message : 'The menu could not be loaded')

/** The menu to browse. Loaded when the screen opens; `reload` picks up a menu change. */
export function useMenu() {
  const [menu, setMenu] = useState<Menu | null>(null)
  const [error, setError] = useState('')

  const reload = useCallback(() => {
    api
      .menu()
      .then((fresh) => {
        setMenu(fresh)
        setError('')
      })
      .catch((e: unknown) => setError(describe(e)))
  }, [])

  useEffect(() => {
    // Fetching the menu is syncing with the server, not derived state.
    // oxlint-disable-next-line react/set-state-in-effect
    reload()
  }, [reload])

  return { menu, error, reload }
}
