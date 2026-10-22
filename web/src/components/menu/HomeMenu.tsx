import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { pictureOf, popular } from '../../lib/menu'
import type { Dish, Menu } from '../../types'
import { VegSwitch } from '../../ui/VegSwitch'
import { CategoryTiles } from './CategoryTiles'
import { DishGrid } from './DishGrid'

/** The home screen: a greeting, the sections as tiles, and below them the popular dishes or the
 * open section's dishes. Opening a section folds the greeting away and titles the dishes. */
export function HomeMenu({
  menu,
  category,
  onCategory,
  onOpen,
}: {
  menu: Menu
  category: string | null // the open section's slug
  onCategory: (slug: string | null) => void
  onOpen: (dish: Dish) => void
}) {
  const sections = useMemo(
    () => menu.categories.filter((c) => menu.dishes.some((d) => d.category === c.slug)),
    [menu],
  )
  const [vegOnly, setVegOnly] = useState(false)
  const scroller = useRef<HTMLElement>(null)
  const active = sections.find((c) => c.slug === category) ?? null
  const shelf = active ? menu.dishes.filter((d) => d.category === active.slug) : popular(menu)
  const dishes = shelf.filter((d) => !vegOnly || d.veg === 'veg')

  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 })
  }, [category])

  return (
    <main ref={scroller} className="relative min-h-0 flex-1 overflow-y-auto px-6 pb-8">
      {/* Only transform and opacity are animated: they run without repainting the dishes. The
          greeting fades out where it stands, and everything below slides up into its place. */}
      <AnimatePresence initial={false} mode="popLayout">
        {!active && (
          <motion.h1
            key="greeting"
            className="pt-6 text-4xl leading-tight font-black landscape:text-5xl"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            Hey,
            <br />
            <span className="font-normal">what's up?</span>
          </motion.h1>
        )}
      </AnimatePresence>
      <motion.div layout="position" transition={{ type: 'spring', stiffness: 320, damping: 34 }} className="will-change-transform">
        <div className="mt-6">
          <CategoryTiles
            categories={sections}
            pictureOf={(c) => pictureOf(menu, c)}
            active={active?.slug ?? null}
            onSelect={onCategory}
          />
        </div>
        <div className="mt-8 flex flex-col items-start gap-3">
          <h2 className={`font-black ${active ? 'text-4xl landscape:text-5xl' : 'text-3xl'}`}>{active?.name ?? 'Popular'}</h2>
          <VegSwitch on={vegOnly} onToggle={() => setVegOnly((on) => !on)} />
        </div>
        <div className="mt-4">
          <DishGrid dishes={dishes} shelf={`${active?.slug ?? 'popular'}-${vegOnly}`} onOpen={onOpen} />
        </div>
      </motion.div>
    </main>
  )
}
