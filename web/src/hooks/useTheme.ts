import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'

const NIGHT_FROM = 19 // the reference kiosk goes dark in the evening
const NIGHT_TO = 7

const byClock = (): Theme => {
  const hour = new Date().getHours()
  return hour >= NIGHT_FROM || hour < NIGHT_TO ? 'dark' : 'light'
}

/** Light by day and dark at night, following the clock, until someone taps the toggle. */
export function useTheme() {
  const [clock, setClock] = useState<Theme>(byClock)
  const [chosen, setChosen] = useState<Theme | null>(null)
  const theme = chosen ?? clock

  useEffect(() => {
    const timer = window.setInterval(() => setClock(byClock()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  return { theme, toggle: () => setChosen(theme === 'dark' ? 'light' : 'dark') }
}
