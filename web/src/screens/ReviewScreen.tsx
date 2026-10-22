import { AnimatePresence } from 'motion/react'
import { Logo } from '../components/Logo'
import { ReviewLine } from '../components/order/ReviewLine'
import { rupees } from '../format'
import type { Order, OrderLine } from '../types'
import { Button } from '../ui/Button'
import { ChevronLeftIcon } from '../ui/Icons'

/** The last look before the order is placed, on the green screen. */
export function ReviewScreen({
  order,
  pictureOf,
  busy,
  onBack,
  onQuantity,
  onRemove,
  onPlace,
}: {
  order: Order | null
  pictureOf: (line: OrderLine) => string | null
  busy: boolean
  onBack: () => void
  onQuantity: (line: number, quantity: number) => void
  onRemove: (line: number) => void
  onPlace: () => void
}) {
  const lines = order?.lines ?? []
  return (
    <main className="flex h-full flex-col bg-review px-6 py-6 text-white landscape:px-16">
      <div className="flex items-center justify-between">
        <button type="button" onClick={onBack} className="flex min-h-12 items-center gap-1 rounded-xl pr-3 text-lg font-bold hover:bg-white/10">
          <ChevronLeftIcon width={28} height={28} />
          Back
        </button>
        <Logo className="h-12" />
        <span className="w-20" />
      </div>
      <h1 className="mt-6 text-5xl leading-tight font-black">
        My
        <br />
        Order
      </h1>
      <p className="font-serif text-lg text-white/70">Drive-thru</p>

      <ul className="mt-6 min-h-0 flex-1 divide-y divide-white/15 overflow-y-auto border-t border-white/15">
        <AnimatePresence initial={false}>
          {lines.map((line) => (
            <ReviewLine
              key={line.id}
              line={line}
              picture={pictureOf(line)}
              busy={busy}
              onQuantity={(quantity) => onQuantity(line.id, quantity)}
              onRemove={() => onRemove(line.id)}
            />
          ))}
        </AnimatePresence>
        {lines.length === 0 && <li className="py-8 text-center text-white/70">Your order is empty.</li>}
      </ul>

      <footer className="flex items-end justify-between gap-6 pt-4">
        <div>
          {order && (
            <p className="text-sm text-white/70">
              Subtotal {rupees(order.subtotal)} · GST {rupees(order.gst)}
            </p>
          )}
          <p className="font-serif text-lg text-white/70">Total</p>
          <p className="text-4xl font-black tabular-nums">{rupees(order?.total ?? 0)}</p>
        </div>
        <Button size="lg" disabled={busy || lines.length === 0} onClick={onPlace}>
          Place order
        </Button>
      </footer>
    </main>
  )
}
