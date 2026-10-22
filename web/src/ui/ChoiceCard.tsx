import { motion } from 'motion/react'
import { CheckIcon } from './Icons'

/** One answer to a question, as a large card: the name, a price note, and a tick when chosen. */
export function ChoiceCard({
  title,
  note,
  selected,
  stacked = false,
  onClick,
}: {
  title: string
  note?: string
  selected: boolean
  stacked?: boolean // the note goes under the title, for cards that sit side by side
  onClick: () => void
}) {
  return (
    <motion.button
      type="button"
      role="radio"
      aria-checked={selected}
      whileTap={{ scale: 0.97 }}
      onClick={onClick}
      className={`relative flex min-h-16 min-w-0 gap-3 rounded-(--radius-tile) border-2 px-4 py-3 text-left transition-colors ${
        stacked ? 'flex-col justify-center' : 'items-center justify-between'
      } ${selected ? 'border-accent bg-accent-soft' : 'border-transparent bg-tile hover:border-line'}`}
    >
      <span className="min-w-0 text-sm leading-snug font-medium break-words">{title}</span>
      <span className={`flex items-center gap-2 text-xs text-muted ${stacked ? 'absolute top-2 right-2' : 'shrink-0'}`}>
        {!stacked && note}
        {selected && (
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent text-on-accent">
            <CheckIcon width={16} height={16} />
          </span>
        )}
      </span>
      {stacked && note && <span className="text-xs text-muted">{note}</span>}
    </motion.button>
  )
}
