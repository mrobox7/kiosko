import { plainName, rupees } from '../../format'
import type { Dish } from '../../types'
import { ChoiceCard } from '../../ui/ChoiceCard'

/** Alone, or as a Medium or Large meal. Only dishes that have meals show this. */
export function MealChoice({ dish, size, onChange }: { dish: Dish; size: string | null; onChange: (size: string | null) => void }) {
  return (
    <fieldset className="space-y-3">
      <legend className="text-lg font-bold">Make it a meal?</legend>
      <div role="radiogroup" aria-label="Meal size" className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <ChoiceCard title={plainName(dish.name)} stacked selected={size === null} onClick={() => onChange(null)} />
        {dish.meal_offers.map((offer) => (
          <ChoiceCard
            key={offer.size}
            title={`${offer.size} meal`}
            note={`+${rupees(offer.price_delta)}`}
            stacked
            selected={size === offer.size}
            onClick={() => onChange(offer.size)}
          />
        ))}
      </div>
    </fieldset>
  )
}
