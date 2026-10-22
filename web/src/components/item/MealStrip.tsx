import { plainName, rupees } from '../../format'
import type { Dish } from '../../types'
import { DishImage } from '../../ui/DishImage'

/** The strip along the bottom of a dish's sheet that offers to make it a meal. */
export function MealStrip({ dish, chosen, onOpen }: { dish: Dish; chosen: string | null; onOpen: () => void }) {
  const offer = dish.meal_offers.find((o) => o.size === chosen) ?? dish.meal_offers[0]
  return (
    <button type="button" onClick={onOpen} className="flex w-full items-center justify-between gap-4 rounded-(--radius-tile) bg-tile px-6 py-4 text-left">
      <span className="text-lg leading-tight font-bold">
        Make it
        <br />a meal
      </span>
      <span className="flex items-center gap-3">
        <DishImage src={dish.image_url} name={dish.name} className="h-12 w-16" />
        <span className="text-sm leading-snug">
          <span className="block font-bold">{chosen ? `${chosen} meal ✓` : `${plainName(offer.size)} meal`}</span>
          <span className="font-bold text-accent">+{rupees(offer.price_delta)}</span>
        </span>
      </span>
    </button>
  )
}
