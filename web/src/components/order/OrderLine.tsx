import { motion } from 'motion/react'
import { plainName, rupees } from '../../format'
import type { OrderLine as Line } from '../../types'
import { DishImage } from '../../ui/DishImage'
import { TrashIcon } from '../../ui/Icons'
import { IconButton } from '../../ui/IconButton'
import { Stepper } from '../../ui/Stepper'

/** One line in the side panel: picture, name, price, and the buttons that change it. */
export function OrderLine({
  line,
  picture,
  busy,
  onQuantity,
  onRemove,
}: {
  line: Line
  picture: string | null
  busy: boolean
  onQuantity: (quantity: number) => void
  onRemove: () => void
}) {
  const details = [line.meal_size ? `${line.meal_size} meal` : '', ...line.options.map(plainName)].filter(Boolean)
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 28, scale: 0.94 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: 30 }}
      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
      className="flex flex-col items-center gap-1.5 border-b border-line py-3 text-center landscape:flex-row landscape:gap-3 landscape:text-left"
    >
      <DishImage src={picture} name={line.name} className="h-14 w-14 shrink-0 rounded-xl" />
      {/* Stacked and centered in the narrow panel; image, text and buttons side by side when wide. */}
      <div className="flex min-w-0 flex-col items-center gap-0.5 landscape:flex-1 landscape:items-start">
        <p className="text-sm leading-snug font-bold">{plainName(line.name)}</p>
        {details.length > 0 && <p className="text-xs text-muted">{details.join(' · ')}</p>}
        {line.note && <p className="text-xs italic text-muted">{line.note}</p>}
        <p className="font-serif text-sm text-muted">{rupees(line.line_total)}</p>
      </div>
      <fieldset disabled={busy} className="flex shrink-0 items-center gap-1">
        <Stepper value={line.quantity} min={1} max={20} label={plainName(line.name)} onChange={onQuantity} />
        <IconButton label={`Remove ${plainName(line.name)}`} className="h-8! w-8!" onClick={onRemove}>
          <TrashIcon width={16} height={16} />
        </IconButton>
      </fieldset>
    </motion.li>
  )
}
