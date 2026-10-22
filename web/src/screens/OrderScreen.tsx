import { useMemo, useState } from 'react'
import { AssistantPanel } from '../components/assistant/AssistantPanel'
import { ItemSheet } from '../components/item/ItemSheet'
import { HomeMenu } from '../components/menu/HomeMenu'
import { OrderPanel } from '../components/order/OrderPanel'
import { TopBar } from '../components/TopBar'
import { useAssistant } from '../hooks/useAssistant'
import type { useOrder } from '../hooks/useOrder'
import type { Dish, LineRequest, Menu, OrderLine, SessionInfo } from '../types'
import { ConfirmSheet } from '../ui/ConfirmSheet'
import { Toast } from '../ui/Toast'
import { ReviewScreen } from './ReviewScreen'

/** Ordering: the menu with "My Order" beside it, a dish's sheet, the assistant, and the review
 * before placing. Created once per order, so a new order starts with a fresh conversation. */
export function OrderScreen({
  menu,
  session,
  order,
  poke,
}: {
  menu: Menu
  session: SessionInfo
  order: ReturnType<typeof useOrder>
  poke: () => void
}) {
  const [dish, setDish] = useState<{ dish: Dish | null; opened: number; open: boolean }>({
    dish: null,
    opened: 0,
    open: false,
  })
  const [category, setCategory] = useState<string | null>(null)
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [confirmingStartOver, setConfirmingStartOver] = useState(false)
  const assistant = useAssistant(session, order.refresh, poke)
  const lines = session.order?.lines.length ?? 0

  const dishes = useMemo(() => new Map(menu.dishes.map((d) => [d.id, d])), [menu])
  const byName = useMemo(() => new Map(menu.dishes.map((d) => [d.name, d])), [menu])
  const pictureOf = (line: OrderLine) => ((line.dish_id === null ? undefined : dishes.get(line.dish_id)) ?? byName.get(line.name))?.image_url ?? null

  async function add(line: LineRequest) {
    if (await order.addLine(line)) setDish((d) => ({ ...d, open: false }))
  }

  const onQuantity = (line: number, quantity: number) => void order.setQuantity(line, quantity)
  const onRemove = (line: number) => void order.removeLine(line)

  return (
    <>
      {reviewing ? (
        <ReviewScreen
          order={session.order}
          pictureOf={pictureOf}
          busy={order.pending}
          onBack={() => setReviewing(false)}
          onQuantity={onQuantity}
          onRemove={onRemove}
          onPlace={() => void order.place()}
        />
      ) : (
        <div className="flex h-full">
          <div className="flex min-w-0 flex-1 flex-col">
            <TopBar
              outletName={menu.outlet.name}
              onBack={category ? () => setCategory(null) : undefined}
              onAsk={() => setAssistantOpen(true)}
              onStartOver={() => (lines > 0 ? setConfirmingStartOver(true) : order.leave())}
            />
            <HomeMenu
              menu={menu}
              category={category}
              onCategory={setCategory}
              onOpen={(d) => setDish((s) => ({ dish: d, opened: s.opened + 1, open: true }))}
            />
          </div>
          <OrderPanel
            order={session.order}
            pictureOf={pictureOf}
            busy={order.pending}
            onQuantity={onQuantity}
            onRemove={onRemove}
            onDone={() => setReviewing(true)}
          />
        </div>
      )}

      <ItemSheet
        dish={dish.dish}
        opened={dish.opened}
        open={dish.open}
        busy={order.pending}
        onAdd={(line) => void add(line)}
        onClose={() => setDish((d) => ({ ...d, open: false }))}
      />

      <AssistantPanel
        open={assistantOpen}
        messages={assistant.messages}
        customerName={session.customer?.name ?? 'You'}
        busy={assistant.busy}
        error={assistant.error}
        voice={assistant.voice}
        onSend={(text) => void assistant.send(text)}
        onClose={() => setAssistantOpen(false)}
      />

      <ConfirmSheet
        open={confirmingStartOver}
        title="Start over?"
        body="Everything in your order will be removed."
        confirmLabel="Start over"
        onConfirm={() => order.leave()}
        onCancel={() => setConfirmingStartOver(false)}
      />

      <Toast message={order.error} onDismiss={order.dismissError} />
    </>
  )
}
