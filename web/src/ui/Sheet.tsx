import { AnimatePresence, motion } from 'motion/react'
import { useEffect, type ReactNode } from 'react'

/** A panel over the screen: a dialog in the middle on a wide screen, rising from the bottom on a
 * tall one. Tapping outside it, or Escape, closes it. */
export function Sheet({
  open,
  label,
  narrow = false,
  onClose,
  children,
}: {
  open: boolean
  label: string
  narrow?: boolean // a dialog about the width of a phone, for one dish
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-40 flex items-end justify-center landscape:items-center landscape:p-6">
          <motion.div
            className="absolute inset-0 bg-black/55"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.section
            role="dialog"
            aria-modal
            aria-label={label}
            className={`relative flex max-h-full w-full flex-col overflow-hidden rounded-t-[2rem] bg-surface shadow-lift landscape:rounded-[2rem] ${narrow ? 'landscape:max-w-lg' : 'landscape:max-w-4xl'}`}
            initial={{ opacity: 0, y: 60, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 60, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 380, damping: 36 }}
          >
            {children}
          </motion.section>
        </div>
      )}
    </AnimatePresence>
  )
}
