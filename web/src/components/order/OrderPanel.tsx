import { AnimatePresence } from 'motion/react'
import { useEffect, useRef } from 'react'
import type { Order, OrderLine as Line } from '../../types'
import { Button } from '../../ui/Button'
import { OrderLine } from './OrderLine'
import { OrderTotals } from './OrderTotals'

/** "My Order": always beside the menu, so the order is edited without leaving it. */
export function OrderPanel({
  order,
  pictureOf,
  busy,
  onQuantity,
  onRemove,
  onDone,
}: {
  order: Order | null
  pictureOf: (line: Line) => string | null
  busy: boolean
  onQuantity: (line: number, quantity: number) => void
  onRemove: (line: number) => void
  onDone: () => void
}) {
  const lines = order?.lines ?? []
  const end = useRef<HTMLDivElement>(null)
  const count = lines.length

  useEffect(() => {
    // A line that was just added slides in at the bottom: bring it into view.
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [count])

  return (
    <aside className="flex w-60 shrink-0 flex-col gap-3 bg-panel p-4 landscape:w-[28rem] landscape:p-6">
      <header>
        <h2 className="text-2xl leading-tight font-black">
          My
          <br />
          Order
        </h2>
        <p className="font-serif text-sm text-muted">Drive-thru</p>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto border-t border-line">
        {lines.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted">Tap a dish to start your order.</p>
        ) : (
          <ul>
            <AnimatePresence initial={false}>
              {lines.map((line) => (
                <OrderLine
                  key={line.id}
                  line={line}
                  picture={pictureOf(line)}
                  busy={busy}
                  onQuantity={(quantity) => onQuantity(line.id, quantity)}
                  onRemove={() => onRemove(line.id)}
                />
              ))}
            </AnimatePresence>
          </ul>
        )}
        <div ref={end} />
      </div>
      {order && lines.length > 0 && <OrderTotals order={order} />}
      <Button size="lg" className="h-24! w-24! self-center rounded-3xl! px-0!" disabled={busy || lines.length === 0} onClick={onDone}>
        Done
      </Button>
    </aside>
  )
}
