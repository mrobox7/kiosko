import { AnimatePresence, motion } from 'motion/react'
import { Button } from '../ui/Button'
import { ChatIcon, ChevronLeftIcon, RetryIcon } from '../ui/Icons'
import { IconButton } from '../ui/IconButton'
import { Brand } from './Brand'

/** The logo, or "Back" while a category is open; "Ask DishPatch"; and a round button that starts
 * the order over. */
export function TopBar({
  outletName,
  onBack,
  onAsk,
  onStartOver,
}: {
  outletName: string
  onBack?: () => void // set while a category is open
  onAsk: () => void
  onStartOver: () => void
}) {
  return (
    <header className="flex items-center justify-between gap-3 px-6 pt-5 pb-1">
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={onBack ? 'back' : 'brand'}
          initial={{ opacity: 0, x: -12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -12 }}
          transition={{ duration: 0.15 }}
        >
          {onBack ? (
            <button type="button" onClick={onBack} className="flex min-h-12 items-center gap-1 rounded-xl pr-3 text-lg font-bold hover:bg-tile">
              <ChevronLeftIcon width={28} height={28} />
              Back
            </button>
          ) : (
            <Brand name={outletName} />
          )}
        </motion.div>
      </AnimatePresence>
      <div className="flex items-center gap-2">
        <Button onClick={onAsk}>
          <ChatIcon width={20} height={20} />
          Ask DishPatch
        </Button>
        <IconButton label="Start over" className="bg-tile" onClick={onStartOver}>
          <RetryIcon width={22} height={22} />
        </IconButton>
      </div>
    </header>
  )
}
