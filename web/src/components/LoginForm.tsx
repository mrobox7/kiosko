import { useState } from 'react'
import { api } from '../api'
import type { SessionInfo } from '../types'

const field =
  'w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-amber-600 focus:ring-2 focus:ring-amber-200'

export function LoginForm({ onLogin }: { onLogin: (session: SessionInfo) => void }) {
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      onLogin(await api.login({ name, phone, email }))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full items-center justify-center bg-stone-100 p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-stone-200"
      >
        <div>
          <h1 className="text-2xl font-semibold text-stone-900">DishPatch</h1>
          <p className="text-sm text-stone-500">Tell us who you are to start.</p>
        </div>
        <input className={field} placeholder="Phone number" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <input className={field} placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className={field} placeholder="Name (only if you are new)" value={name} onChange={(e) => setName(e.target.value)} />
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <button
          disabled={busy}
          className="w-full rounded-lg bg-amber-700 px-3 py-2 text-sm font-medium text-white hover:bg-amber-800 disabled:opacity-50"
        >
          {busy ? 'Starting…' : 'Start'}
        </button>
      </form>
    </div>
  )
}
