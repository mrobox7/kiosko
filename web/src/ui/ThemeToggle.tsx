import type { Theme } from '../hooks/useTheme'
import { MoonIcon, SunIcon } from './Icons'

/** The small light/dark switch from the reference's start screen. */
export function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const dark = theme === 'dark'
  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label="Dark theme"
      onClick={(event) => {
        event.stopPropagation()
        onToggle()
      }}
      className="flex min-h-12 items-center gap-2 rounded-full bg-surface pr-6 pl-4 text-sm font-semibold text-ink shadow-card"
    >
      {dark ? <MoonIcon width={20} height={20} /> : <SunIcon width={20} height={20} />}
      {dark ? 'Dark' : 'Light'}
    </button>
  )
}
