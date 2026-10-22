import { plainName, rupees } from '../../format'
import type { Dish } from '../../types'
import { DishImage } from '../../ui/DishImage'
import { VegMark } from '../../ui/VegMark'

/** One dish: a small picture with no frame, its name and its price. Tapping it opens its sheet.
 * Smaller and lighter than a category tile, as in the reference. The space above the picture holds
 * the Bestseller pill, so it never covers it; the veg mark sits on the picture, bottom left. */
export function DishCard({ dish, onOpen }: { dish: Dish; onOpen: (dish: Dish) => void }) {
  return (
    <li className="flex">
      <button
        type="button"
        onClick={() => onOpen(dish)}
        className="relative flex w-full min-w-0 flex-col items-center gap-1.5 rounded-(--radius-tile) p-2 pt-8 text-center transition duration-100 hover:bg-tile active:scale-95"
      >
        {dish.tags.includes('bestseller') && (
          <span className="absolute top-2 left-2 inline-flex items-center rounded-full bg-promo px-2 py-1 text-[10px] leading-none font-semibold text-white">Bestseller</span>
        )}
        <div className="relative w-full">
          <DishImage src={dish.image_url} name={dish.name} className="h-[3.85rem] w-full" />
          <span className="absolute bottom-0 left-0">
            <VegMark veg={dish.veg} small />
          </span>
        </div>
        <h3 className="line-clamp-2 w-full min-w-0 text-xs leading-snug font-medium break-words">{plainName(dish.name)}</h3>
        <span className="mt-auto text-xs font-semibold text-accent">{rupees(dish.base_price)}</span>
      </button>
    </li>
  )
}
