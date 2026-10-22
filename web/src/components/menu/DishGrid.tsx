import { motion } from 'motion/react'
import type { Dish } from '../../types'
import { DishCard } from './DishCard'

/** The dishes of one shelf. `shelf` names what is shown (a category, popular, veg only): when it
 * changes the whole grid fades in as one block, which is much cheaper than animating every card. */
export function DishGrid({ dishes, shelf, onOpen }: { dishes: Dish[]; shelf: string; onOpen: (dish: Dish) => void }) {
  if (dishes.length === 0) return <p className="p-8 text-center text-lg text-muted">Nothing here right now.</p>
  return (
    <motion.ul
      key={shelf}
      className="grid grid-cols-[repeat(auto-fill,minmax(7rem,1fr))] gap-3 will-change-[opacity,transform]"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      {dishes.map((dish) => (
        <DishCard key={dish.id} dish={dish} onOpen={onOpen} />
      ))}
    </motion.ul>
  )
}
