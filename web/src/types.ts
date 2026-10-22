// Shapes of the Python API (app/api/schemas.py).

export interface Customer {
  id: number
  name: string | null // a customer who gave a number but no name
}

export interface OrderLine {
  id: number
  dish_id: number | null // the dish, for its picture
  name: string
  quantity: number
  meal_size: string | null
  options: string[]
  note: string | null
  line_total: number // rupees
}

/** The order so far; once placed it has its number. Prices are in rupees, GST is in the total. */
export interface Order {
  id: number
  status: string
  order_number: number | null
  lines: OrderLine[]
  subtotal: number
  gst: number
  total: number
}

export interface SessionInfo {
  session_id: string
  status: 'open' | 'placed' | 'abandoned'
  customer: Customer | null // null until the customer gives a phone number
  order: Order | null // null until the first dish is added
  greeting: string | null
  voice: boolean // the server can take voice
  idle_timeout_s: number // seconds without a message after which the server ends the chat
}

export type TraceEvent = { event: string } & Record<string, unknown>

export interface Reply {
  text: string
  stop_reason: string
  trace: TraceEvent[]
}

/** A reply that came over the voice socket: the same reply plus how the speaking went. */
export interface VoiceReply extends Reply {
  first_audio_ms: number | null
  speech_error: string | null // set when the reply could not be spoken
  interrupted: boolean // the customer cut the speech off; the text is still the full reply
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  trace?: TraceEvent[]
}

// The menu (GET /api/menu).

export interface MenuOption {
  id: number
  name: string
  price_delta: number // rupees added when picked
  is_default: boolean // taken when a required question is left unanswered
}

/** A question on a dish: pick between `min_select` and `max_select` of the options in all. */
export interface OptionGroup {
  id: number
  name: string
  min_select: number
  max_select: number
  options: MenuOption[]
}

/** Making a dish a meal: a size, what it adds, and the side and drink to choose from. */
export interface MealOffer {
  size: string
  price_delta: number
  side: OptionGroup | null // a Large meal has no side question
  drink: OptionGroup
}

export interface Dish {
  id: number
  name: string
  description: string | null
  kind: string // item | combo
  veg: string // veg | non_veg
  category: string // a category slug
  base_price: number
  tags: string[]
  nutrition: Record<string, number | string>
  allergens: string[]
  option_groups: OptionGroup[]
  meal_offers: MealOffer[]
  image_url: string | null
}

export interface Category {
  slug: string
  name: string
}

export interface Outlet {
  code: string
  name: string
  address: string
}

export interface Menu {
  version: string
  outlet: Outlet
  categories: Category[]
  dishes: Dish[]
}

/** A dish added from the screen, with its choices made. */
export interface LineRequest {
  dish_id: number
  quantity: number
  meal_size?: string
  options: { option_id: number; qty: number }[]
}
