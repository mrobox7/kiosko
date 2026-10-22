import { AnimatePresence, motion } from 'motion/react'
import { rupees } from '../../format'
import type { Order } from '../../types'

function Row({ label, amount }: { label: string; amount: number }) {
  return (
    <div className="flex justify-between text-xs text-muted">
      <dt>{label}</dt>
      <dd className="tabular-nums">{rupees(amount)}</dd>
    </div>
  )
}

/** Subtotal and GST in small type, then the total, which flips when it changes. */
export function OrderTotals({ order }: { order: Order }) {
  return (
    <dl className="space-y-1 border-t border-line pt-3 text-center">
      <Row label="Subtotal" amount={order.subtotal} />
      <Row label="GST" amount={order.gst} />
      <dt className="pt-2 font-serif text-sm text-muted">Total</dt>
      <dd className="relative h-9 overflow-hidden text-2xl font-black tabular-nums">
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={order.total}
            className="block"
            initial={{ y: 24, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -24, opacity: 0 }}
          >
            {rupees(order.total)}
          </motion.span>
        </AnimatePresence>
      </dd>
    </dl>
  )
}
