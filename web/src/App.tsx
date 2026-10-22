import { useCallback } from 'react'
import { KEEPALIVE_MS, TIMED_OUT, useOrder } from './hooks/useOrder'
import { useIdle } from './hooks/useIdle'
import { useMenu } from './hooks/useMenu'
import { useTheme } from './hooks/useTheme'
import { OrderScreen } from './screens/OrderScreen'
import { PlacedScreen } from './screens/PlacedScreen'
import { WelcomeScreen } from './screens/WelcomeScreen'

export default function App() {
  const { menu, error: menuError, reload } = useMenu()
  const order = useOrder(reload)
  const { session } = order
  const { theme, toggle } = useTheme()

  // The server ends an order nobody has touched for `idle_timeout_s`. The screen gives up a little
  // earlier, so it is the one that ends it and the customer sees why.
  const poke = useIdle({
    enabled: session?.status === 'open',
    ms: Math.max(10_000, (session?.idle_timeout_s ?? 0) * 1000 - 1.5 * KEEPALIVE_MS),
    onIdle: () => order.leave(TIMED_OUT),
    onActive: order.keepAlive,
  })
  const done = useCallback(() => order.leave(), [order])

  if (session?.status === 'placed' && session.order) return <PlacedScreen order={session.order} onDone={done} />
  if (session && menu) return <OrderScreen key={session.session_id} menu={menu} session={session} order={order} poke={poke} />

  return (
    <WelcomeScreen
      ready={menu !== null}
      starting={order.starting}
      notice={order.notice}
      error={order.error || menuError}
      theme={theme}
      onToggleTheme={toggle}
      onStart={() => void order.start()}
      onRetry={() => (menuError ? reload() : void order.start())}
    />
  )
}
