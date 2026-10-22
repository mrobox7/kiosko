import { motion } from 'motion/react'
import { useEffect } from 'react'
import { plainName, rupees } from '../format'
import type { Order } from '../types'
import { Button } from '../ui/Button'

const RESET_MS = 20_000

/** Shown once the order is placed: the number to remember and what was ordered. It gives way to
 * the welcome screen by itself, ready for the next car. */
export function PlacedScreen({ order, onDone }: { order: Order; onDone: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, RESET_MS)
    return () => window.clearTimeout(timer)
  }, [onDone])

  return (
    <main className="flex h-full flex-col items-center justify-center gap-6 bg-review p-8 text-center text-white">
      <p className="text-xl font-semibold tracking-wide uppercase text-white/80">Your order number</p>
      <motion.p
        className="text-9xl font-black tabular-nums"
        initial={{ scale: 0.6, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 260, damping: 18 }}
      >
        {order.order_number ?? '–'}
      </motion.p>
      <ul className="space-y-1 text-lg">
        {order.lines.map((line) => (
          <li key={line.id}>
            {line.quantity} × {plainName(line.name)}
            {line.meal_size ? ` (${line.meal_size} meal)` : ''}
          </li>
        ))}
      </ul>
      <p className="text-2xl font-black">Total {rupees(order.total)} (GST included)</p>
      <p className="font-serif text-lg text-white/80">Please drive to the next window.</p>
      <Button size="lg" onClick={onDone}>
        Next customer
      </Button>
    </main>
  )
}
