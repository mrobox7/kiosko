import type { SessionInfo } from '../types'

function when(iso: string) {
  return new Date(iso).toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function Sidebar({
  session,
  open,
  busy,
  onClose,
  onNewChat,
  onSignOut,
}: {
  session: SessionInfo
  open: boolean
  busy: boolean
  onClose: () => void
  onNewChat: () => void
  onSignOut: () => void
}) {
  return (
    <>
      {/* On a phone the sidebar is a drawer over the chat; tapping outside closes it. */}
      {open && <div className="fixed inset-0 z-10 bg-black/30 md:hidden" onClick={onClose} />}
      <aside
        inert={!open}
        className={
          'fixed inset-y-0 left-0 z-20 flex w-72 shrink-0 flex-col gap-6 border-r border-stone-200 bg-white p-5 shadow-xl transition-all duration-200 md:static md:z-auto md:translate-x-0 md:shadow-none ' +
          (open ? 'translate-x-0 md:ml-0' : '-translate-x-full md:-ml-72')
        }
      >
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs uppercase tracking-wide text-stone-400">Signed in as</p>
            <p className="text-lg font-semibold text-stone-900">{session.customer.name}</p>
          </div>
          <button onClick={onClose} aria-label="Close sidebar" className="rounded-lg p-1 text-stone-400 hover:bg-stone-100 md:hidden">
            <svg width={20} height={20} viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.3 5.71 12 12.01l-6.3-6.3-1.4 1.41 6.29 6.29-6.3 6.3 1.42 1.41 6.29-6.3 6.3 6.3 1.41-1.42-6.3-6.29 6.3-6.3z" />
            </svg>
          </button>
        </div>

        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">Remembered</h2>
          {session.memory_unavailable ? (
            <p className="text-sm text-amber-700">Saved preferences could not be loaded.</p>
          ) : session.remembered.length ? (
            <ul className="space-y-1 text-sm text-stone-700">
              {session.remembered.map((f) => (
                <li key={f.label}>
                  <span className="font-medium">{f.label}:</span> {f.value}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-stone-400">Nothing saved yet.</p>
          )}
        </section>

        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">Upcoming bookings</h2>
          {session.upcoming === null ? (
            <p className="text-sm text-amber-700">Bookings could not be loaded.</p>
          ) : session.upcoming.length ? (
            <ul className="space-y-2 text-sm text-stone-700">
              {session.upcoming.map((b) => (
                <li key={b.id} className="rounded-lg bg-stone-50 px-3 py-2 ring-1 ring-stone-200">
                  <p className="font-medium">#{b.id} · {when(b.slot_datetime)}</p>
                  <p className="text-stone-500">Party of {b.party_size} · table {b.table_id}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-stone-400">None.</p>
          )}
        </section>

        <div className="mt-auto space-y-2">
          <button
            onClick={onNewChat}
            disabled={busy}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm hover:bg-stone-50 disabled:opacity-50"
          >
            New chat
          </button>
          <button onClick={onSignOut} className="w-full rounded-lg px-3 py-2 text-sm text-stone-500 hover:bg-stone-50">
            Sign out
          </button>
        </div>
      </aside>
    </>
  )
}
