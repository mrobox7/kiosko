import type { Dish } from '../../types'

/** Calories and allergens, with the reminder that they are estimates. */
export function DishFacts({ dish }: { dish: Dish }) {
  const kcal = Number(dish.nutrition.calories_kcal)
  return (
    <div className="space-y-2 text-sm text-muted">
      {Number.isFinite(kcal) && kcal > 0 && <p>About {Math.round(kcal)} kcal</p>}
      {dish.allergens.length > 0 && (
        <p>
          Contains: <span className="font-semibold text-ink">{dish.allergens.join(', ')}</span>
        </p>
      )}
      <p className="text-xs">Allergen and nutrition details are estimates, not official.</p>
    </div>
  )
}
