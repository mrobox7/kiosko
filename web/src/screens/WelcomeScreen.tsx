import { motion } from 'motion/react'
import { Logo } from '../components/Logo'
import type { Theme } from '../hooks/useTheme'
import { Button } from '../ui/Button'
import { ThemeToggle } from '../ui/ThemeToggle'

/** The screen between customers: the logo over the yellow arc. Touching it begins an order. */
export function WelcomeScreen({
  ready,
  starting,
  notice,
  error,
  theme,
  onToggleTheme,
  onStart,
  onRetry,
}: {
  ready: boolean // the menu has loaded
  starting: boolean
  notice: string
  error: string
  theme: Theme
  onToggleTheme: () => void
  onStart: () => void
  onRetry: () => void
}) {
  const failed = error !== ''
  return (
    <main
      className="relative flex h-full flex-col items-center justify-center gap-8 overflow-hidden bg-canvas p-8 text-center"
      onClick={ready && !starting && !failed ? onStart : undefined}
    >
      <div aria-hidden className="absolute top-[66%] left-[30%] landscape:top-[60%] h-[120vmax] w-[120vmax] -translate-x-1/2 rounded-full border-4 border-white bg-accent" />
      <div className="relative flex -translate-y-16 flex-col items-center gap-8">
        <Logo className="h-32 -translate-y-10 landscape:h-36" />
        <motion.h1 className="text-2xl leading-tight font-semibold md:text-3xl" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          What would you
          <br />
          like to order?
        </motion.h1>
        {notice && <p className="max-w-xl rounded-(--radius-tile) bg-surface px-5 py-3 text-lg shadow-card">{notice}</p>}
        {failed && (
          <div className="space-y-4">
            <p className="max-w-xl text-lg font-semibold">{error}</p>
            <Button
              size="lg"
              onClick={(event) => {
                event.stopPropagation()
                onRetry()
              }}
            >
              Try again
            </Button>
          </div>
        )}
      </div>
      {!failed && (
        // On the yellow arc, in black, so it reads in both themes.
        <motion.p
          className="absolute bottom-28 text-xl font-semibold text-on-accent"
          animate={ready && !starting ? { opacity: [0.55, 1, 0.55] } : { opacity: 0.8 }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          {starting ? 'Starting your order…' : ready ? 'Touch to start' : 'Loading the menu…'}
        </motion.p>
      )}
      <div className="absolute bottom-6">
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>
    </main>
  )
}
