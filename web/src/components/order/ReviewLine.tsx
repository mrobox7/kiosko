import { motion } from 'motion/react'
import { plainName, rupees } from '../../format'
import type { OrderLine } from '../../types'
import { DishImage } from '../../ui/DishImage'
import { TrashIcon } from '../../ui/Icons'
import { IconButton } from '../../ui/IconButton'
import { Stepper } from '../../ui/Stepper'

/** One line of the order review, on the green screen. */
export function ReviewLine({
  line,
  picture,
  busy,
  onQuantity,
  onRemove,
}: {
  line: OrderLine
  picture: string | null
  busy: boolean
  onQuantity: (quantity: number) => void
  onRemove: () => void
}) {
  const details = [line.meal_size ? `${line.meal_size} meal` : '', ...line.options.map(plainName)].filter(Boolean)
  return (
    <motion.li
      layout
      initial={{ opacity: 0, x: 30 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -30 }}
      className="flex items-center gap-4 py-4"
    >
      <div className="shrink-0 rounded-2xl bg-white p-2">
        <DishImage src={picture} name={line.name} className="h-16 w-16" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="leading-snug font-bold">{plainName(line.name)}</p>
        {details.length > 0 && <p className="text-sm text-white/70">{details.join(' · ')}</p>}
        <p className="font-serif text-white/80">{rupees(line.line_total)}</p>
      </div>
      <fieldset disabled={busy} className="flex shrink-0 items-center gap-1">
        <Stepper tone="onGreen" value={line.quantity} min={1} max={20} label={plainName(line.name)} onChange={onQuantity} />
        <IconButton label={`Remove ${plainName(line.name)}`} className="h-8! w-8! text-white hover:bg-white/10" onClick={onRemove}>
          <TrashIcon width={16} height={16} />
        </IconButton>
      </fieldset>
    </motion.li>
  )
}
