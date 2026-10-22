import { motion } from 'motion/react'
import type { Category } from '../../types'
import { DishImage } from '../../ui/DishImage'

/** The menu sections as a grid of tiles. The chosen one turns yellow; tapping it again goes back
 * to the popular dishes. Tiles are a little bigger than the dishes below them, as in the reference. */
export function CategoryTiles({
  categories,
  pictureOf,
  active,
  onSelect,
}: {
  categories: Category[]
  pictureOf: (category: Category) => string | null
  active: string | null
  onSelect: (slug: string | null) => void
}) {
  return (
    <nav aria-label="Menu sections" className="grid grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))] gap-3">
      {categories.map((category) => {
        const on = category.slug === active
        return (
          <motion.button
            key={category.slug}
            type="button"
            aria-pressed={on}
            whileTap={{ scale: 0.96 }}
            onClick={() => onSelect(on ? null : category.slug)}
            className={`flex h-32 flex-col items-center justify-center gap-2 rounded-(--radius-tile) p-3 text-center transition-colors ${
              on ? 'bg-accent text-on-accent' : 'bg-tile text-ink'
            }`}
          >
            <DishImage src={pictureOf(category)} name={category.name} className="h-[3.85rem] w-full" />
            <span className="line-clamp-2 text-sm leading-tight font-semibold">{category.name}</span>
          </motion.button>
        )
      })}
    </nav>
  )
}
