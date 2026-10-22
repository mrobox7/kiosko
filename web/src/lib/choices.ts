// What a customer has chosen on a dish's sheet, and the rules that make it complete. The server
// checks every order again; these rules only decide what the sheet lets the customer do.

import { plainName } from '../format'
import type { Dish, LineRequest, MealOffer, OptionGroup } from '../types'

/** group id -> option id -> how many of it. */
export type Picks = Record<number, Record<number, number>>

export interface Choices {
  quantity: number
  mealSize: string | null // null: the dish on its own
  picks: Picks
}

export const noChoices: Choices = { quantity: 1, mealSize: null, picks: {} }

/** What a dish starts with: each required question that has exactly one default option (ketchup
 * on a burger) is already answered, as the server would answer it. */
export function defaultChoices(dish: Dish): Choices {
  const picks: Picks = {}
  for (const group of dish.option_groups) {
    const defaults = group.options.filter((o) => o.is_default)
    if (group.min_select > 0 && defaults.length === 1) picks[group.id] = { [defaults[0].id]: group.min_select }
  }
  return { ...noChoices, picks }
}

export const mealFor = (dish: Dish, choices: Choices): MealOffer | undefined =>
  dish.meal_offers.find((offer) => offer.size === choices.mealSize)

/** Every question that applies now: the dish's own, plus the meal's side and drink. */
export function groupsFor(dish: Dish, choices: Choices): OptionGroup[] {
  const meal = mealFor(dish, choices)
  return [...dish.option_groups, ...(meal ? [meal.side, meal.drink] : [])].filter((g) => g !== null)
}

export const countIn = (choices: Choices, group: OptionGroup) =>
  Object.values(choices.picks[group.id] ?? {}).reduce((sum, qty) => sum + qty, 0)

/** The questions still short of their minimum. */
export const unanswered = (dish: Dish, choices: Choices) =>
  groupsFor(dish, choices).filter((group) => countIn(choices, group) < group.min_select)

/** One of the dish as chosen: price, meal and picked options. Before GST, which is added to the total. */
export function unitPrice(dish: Dish, choices: Choices): number {
  const extras = groupsFor(dish, choices).flatMap((group) =>
    group.options.map((o) => o.price_delta * (choices.picks[group.id]?.[o.id] ?? 0)),
  )
  return dish.base_price + (mealFor(dish, choices)?.price_delta ?? 0) + extras.reduce((a, b) => a + b, 0)
}

/** Pick one more (`by` 1) or one fewer (-1) of an option, within the group's limits. A group that
 * takes a single choice swaps it for the new one. */
export function pick(choices: Choices, group: OptionGroup, optionId: number, by: 1 | -1): Choices {
  const mine = { ...choices.picks[group.id] }
  if (by === -1) {
    const left = (mine[optionId] ?? 0) - 1
    if (left > 0) mine[optionId] = left
    else delete mine[optionId]
  } else if (group.max_select === 1) {
    return { ...choices, picks: { ...choices.picks, [group.id]: { [optionId]: 1 } } }
  } else if (countIn(choices, group) < group.max_select) {
    mine[optionId] = (mine[optionId] ?? 0) + 1
  }
  return { ...choices, picks: { ...choices.picks, [group.id]: mine } }
}

/** Make it a meal of this size, or back to the dish alone (`null`). The old meal's answers go. */
export function setMeal(dish: Dish, choices: Choices, size: string | null): Choices {
  const next = { ...choices, mealSize: size, picks: {} as Picks }
  for (const group of groupsFor(dish, next)) {
    if (choices.picks[group.id]) next.picks[group.id] = choices.picks[group.id]
  }
  return next
}

export function toRequest(dish: Dish, choices: Choices): LineRequest {
  const options = groupsFor(dish, choices).flatMap((group) =>
    Object.entries(choices.picks[group.id] ?? {}).map(([id, qty]) => ({ option_id: Number(id), qty })),
  )
  return {
    dish_id: dish.id,
    quantity: choices.quantity,
    ...(choices.mealSize ? { meal_size: choices.mealSize } : {}),
    options,
  }
}

/** What has been chosen, in words: the meal, then each picked option ("2× Cheese"). */
export function describe(dish: Dish, choices: Choices): string[] {
  const picked = groupsFor(dish, choices).flatMap((group) =>
    group.options
      .filter((o) => choices.picks[group.id]?.[o.id])
      .map((o) => {
        const qty = choices.picks[group.id][o.id]
        return qty > 1 ? `${qty}× ${plainName(o.name)}` : plainName(o.name)
      }),
  )
  return [...(choices.mealSize ? [`${choices.mealSize} meal`] : []), ...picked]
}
