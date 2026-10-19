import { useEffect, useRef, useState } from 'react'
import type { ChatMessage } from '../types'
import type { VoiceState } from '../voice/useVoice'
import { Avatar } from './Avatar'
import { VoiceDock } from './VoiceDock'

function Trace({ trace }: { trace: NonNullable<ChatMessage['trace']> }) {
  return (
    <details className="mt-2 text-xs text-stone-500">
      <summary className="cursor-pointer select-none">Trace</summary>
      <pre className="mt-1 max-h-64 overflow-auto rounded-lg bg-stone-900 p-3 text-stone-100">
        {JSON.stringify(trace, null, 2)}
      </pre>
    </details>
  )
}

export interface VoiceControls {
  state: VoiceState
  handsFree: boolean
  onMic: () => void
  onCancel: () => void
  onHandsFree: () => void
}

// Push-to-talk hints. Hands-free explains itself in the voice dock.
const pushHints: Partial<Record<VoiceState, string>> = {
  recording: 'Recording… tap the mic again to send',
  speaking: 'Speaking… tap the mic to stop',
}

function MicIcon({ state }: { state: VoiceState }) {
  const common = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'currentColor' }
  if (state === 'recording')
    return (
      <svg {...common}>
        <rect x="6" y="6" width="12" height="12" rx="2" />
      </svg>
    )
  if (state === 'speaking')
    return (
      <svg {...common}>
        <path d="M3 10v4h4l5 4V6L7 10H3zm13.5 2a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4z" />
      </svg>
    )
  return (
    <svg {...common}>
      <path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z" />
    </svg>
  )
}

export function ChatPanel({
  messages,
  customerName,
  busy,
  error,
  sidebarOpen,
  onToggleSidebar,
  onSend,
  voice,
}: {
  messages: ChatMessage[]
  customerName: string
  busy: boolean
  error: string
  sidebarOpen: boolean
  onToggleSidebar: () => void
  onSend: (text: string) => void
  voice?: VoiceControls
}) {
  const [draft, setDraft] = useState('')
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    onSend(text)
  }

  const pushHint = voice && !voice.handsFree ? pushHints[voice.state] : undefined

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-stone-100">
      <header className="flex items-center gap-3 border-b border-stone-200 bg-white px-3 py-2.5 md:px-4">
        <button
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
          aria-expanded={sidebarOpen}
          className="rounded-lg p-2 text-stone-600 hover:bg-stone-100"
        >
          <svg width={22} height={22} viewBox="0 0 24 24" fill="currentColor">
            <path d="M3 5h18v2H3V5zm0 6h18v2H3v-2zm0 6h18v2H3v-2z" />
          </svg>
        </button>
        <Avatar who="assistant" />
        <div className="leading-tight">
          <h1 className="text-base font-semibold text-stone-900">DishPatch</h1>
          <p className="text-xs text-stone-500">Your restaurant host</p>
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto p-4 md:p-6">
        {messages.map((m, i) => (
          <div key={i} className={'flex items-end gap-2 ' + (m.role === 'user' ? 'flex-row-reverse' : '')}>
            <Avatar who={m.role} name={customerName} />
            <div
              className={
                'max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm md:max-w-[65%] ' +
                (m.role === 'user'
                  ? 'rounded-br-md bg-amber-700 text-white'
                  : 'rounded-bl-md bg-white text-stone-800 ring-1 ring-stone-200')
              }
            >
              <p className="whitespace-pre-wrap">{m.text}</p>
              {m.trace && <Trace trace={m.trace} />}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex items-end gap-2">
            <Avatar who="assistant" />
            <div className="rounded-2xl rounded-bl-md bg-white px-4 py-3 text-sm text-stone-400 ring-1 ring-stone-200">
              <span className="flex gap-1" aria-label="Thinking">
                {[0, 150, 300].map((delay) => (
                  <span key={delay} className="h-2 w-2 animate-bounce rounded-full bg-stone-400" style={{ animationDelay: `${delay}ms` }} />
                ))}
              </span>
            </div>
          </div>
        )}
        <div ref={end} />
      </div>

      {error && <p className="mx-4 mb-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 md:mx-6">{error}</p>}

      {voice && <VoiceDock state={voice.state} handsFree={voice.handsFree} onToggle={voice.onHandsFree} />}

      {pushHint && (
        <div className="flex items-center gap-3 border-t border-stone-200 bg-white px-4 pt-2 text-xs text-stone-500 md:px-6">
          <span className={voice?.state === 'recording' ? 'animate-pulse text-red-600' : ''}>{pushHint}</span>
          {voice?.state === 'recording' && (
            <button type="button" onClick={voice.onCancel} className="underline hover:text-stone-700">
              Cancel
            </button>
          )}
        </div>
      )}

      <form onSubmit={submit} className="flex gap-2 border-t border-stone-200 bg-white p-3 md:p-4">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="How can we help?"
          autoFocus
          className="min-w-0 flex-1 rounded-full border border-stone-300 bg-white px-4 py-2 text-sm outline-none focus:border-amber-600 focus:ring-2 focus:ring-amber-200"
        />
        {voice && (
          <button
            type="button"
            onClick={voice.onMic}
            disabled={voice.handsFree || voice.state === 'working' || (busy && voice.state === 'idle')}
            aria-label={voice.state === 'recording' ? 'Stop and send' : voice.state === 'speaking' ? 'Stop speaking' : 'Speak'}
            title="Record a voice message"
            className={
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-full disabled:opacity-50 ' +
              (voice.state === 'recording'
                ? 'animate-pulse bg-red-600 text-white'
                : voice.state === 'speaking' && !voice.handsFree
                  ? 'bg-amber-100 text-amber-800 ring-1 ring-amber-300'
                  : 'border border-stone-300 text-stone-600 hover:bg-stone-50')
            }
          >
            <MicIcon state={voice.state} />
          </button>
        )}
        <button
          disabled={busy || !draft.trim()}
          className="rounded-full bg-amber-700 px-5 py-2 text-sm font-medium text-white hover:bg-amber-800 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </main>
  )
}
