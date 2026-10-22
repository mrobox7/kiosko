import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../../types'
import { Avatar } from './Avatar'

function Trace({ trace }: { trace: NonNullable<ChatMessage['trace']> }) {
  return (
    <details className="mt-2 text-xs text-muted">
      <summary className="cursor-pointer select-none">Trace</summary>
      <pre className="mt-1 max-h-64 overflow-auto rounded-lg bg-ink p-3 text-page">{JSON.stringify(trace, null, 2)}</pre>
    </details>
  )
}

function Thinking() {
  return (
    <div className="flex items-end gap-2">
      <Avatar who="assistant" />
      <div className="rounded-2xl rounded-bl-md bg-surface px-4 py-3 ring-1 ring-line">
        <span className="flex gap-1" role="status" aria-label="Thinking">
          {[0, 150, 300].map((delay) => (
            <span key={delay} className="h-2 w-2 animate-bounce rounded-full bg-muted/60" style={{ animationDelay: `${delay}ms` }} />
          ))}
        </span>
      </div>
    </div>
  )
}

/** The conversation so far, newest at the bottom. */
export function MessageList({ messages, customerName, busy }: { messages: ChatMessage[]; customerName: string; busy: boolean }) {
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  return (
    <div className="flex-1 space-y-4 overflow-y-auto bg-tile p-4 md:p-6">
      {messages.map((m, i) => (
        <div key={i} className={'flex items-end gap-2 ' + (m.role === 'user' ? 'flex-row-reverse' : '')}>
          <Avatar who={m.role} name={customerName} />
          <div
            className={
              'max-w-[80%] rounded-2xl px-4 py-2.5 text-base leading-relaxed shadow-sm ' +
              (m.role === 'user' ? 'rounded-br-md bg-accent text-on-accent' : 'rounded-bl-md bg-surface text-ink ring-1 ring-line')
            }
          >
            <p className="whitespace-pre-wrap">{m.text}</p>
            {m.trace && <Trace trace={m.trace} />}
          </div>
        </div>
      ))}
      {busy && <Thinking />}
      <div ref={end} />
    </div>
  )
}
