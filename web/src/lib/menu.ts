import type { Category, Dish, Menu } from '../types'

/** The dishes on the home screen's "Popular" shelf: the bestsellers, or the first few if none. */
export function popular(menu: Menu): Dish[] {
  const hits = menu.dishes.filter((d) => d.tags.includes('bestseller'))
  return hits.length > 0 ? hits : menu.dishes.slice(0, 12)
}

/** The picture on a category's tile: its best-selling dish, or the first one with a picture. */
export function pictureOf(menu: Menu, category: Category): string | null {
  const pictured = menu.dishes.filter((d) => d.category === category.slug && d.image_url)
  return (pictured.find((d) => d.tags.includes('bestseller')) ?? pictured[0])?.image_url ?? null
}
