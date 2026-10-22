import { AnimatePresence, motion } from 'motion/react'
import { useEffect } from 'react'
import { CloseIcon } from './Icons'

const SHOWN_MS = 7000

/** A short message at the bottom of the screen that clears itself. */
export function Toast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  useEffect(() => {
    if (!message) return
    const timer = window.setTimeout(onDismiss, SHOWN_MS)
    return () => window.clearTimeout(timer)
  }, [message, onDismiss])

  return (
    <AnimatePresence>
      {message && (
        <motion.div
          role="alert"
          className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-xl items-center gap-3 rounded-(--radius-tile) bg-ink px-5 py-4 text-page shadow-lift"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 30 }}
        >
          <p className="flex-1 text-base">{message}</p>
          <button type="button" aria-label="Dismiss" onClick={onDismiss} className="rounded-full p-2 hover:bg-page/15">
            <CloseIcon width={20} height={20} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
