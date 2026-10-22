import { useState } from 'react'
import type { VoiceState } from '../../voice/useVoice'
import { VoiceDock } from './VoiceDock'

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

/** The typing box with the microphone, and the voice dock above it when voice is on. */
export function Composer({ busy, voice, onSend }: { busy: boolean; voice?: VoiceControls; onSend: (text: string) => void }) {
  const [draft, setDraft] = useState('')

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const text = draft.trim()
    if (!text || busy) return
    setDraft('')
    onSend(text)
  }

  const pushHint = voice && !voice.handsFree ? pushHints[voice.state] : undefined

  return (
    <>
      {voice && <VoiceDock state={voice.state} handsFree={voice.handsFree} onToggle={voice.onHandsFree} />}

      {pushHint && (
        <div className="flex items-center gap-3 border-t border-line bg-surface px-4 pt-2 text-xs text-muted md:px-6">
          <span className={voice?.state === 'recording' ? 'animate-pulse text-promo' : ''}>{pushHint}</span>
          {voice?.state === 'recording' && (
            <button type="button" onClick={voice.onCancel} className="underline hover:text-ink">
              Cancel
            </button>
          )}
        </div>
      )}

      <form onSubmit={submit} className="flex gap-2 border-t border-line bg-surface p-3 md:p-4">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about the menu, or say what you want"
          className="min-h-12 min-w-0 flex-1 rounded-full border-2 border-transparent bg-tile px-5 text-base outline-none focus:border-accent"
        />
        {voice && (
          <button
            type="button"
            onClick={voice.onMic}
            disabled={voice.handsFree || voice.state === 'working' || (busy && voice.state === 'idle')}
            aria-label={voice.state === 'recording' ? 'Stop and send' : voice.state === 'speaking' ? 'Stop speaking' : 'Speak'}
            title="Record a voice message"
            className={
              'flex h-12 w-12 shrink-0 items-center justify-center rounded-full disabled:opacity-50 ' +
              (voice.state === 'recording'
                ? 'animate-pulse bg-promo text-white'
                : voice.state === 'speaking' && !voice.handsFree
                  ? 'bg-accent-soft text-ink ring-1 ring-accent'
                  : 'bg-tile text-ink hover:bg-line')
            }
          >
            <MicIcon state={voice.state} />
          </button>
        )}
        <button
          disabled={busy || !draft.trim()}
          className="min-h-12 rounded-(--radius-key) bg-accent px-6 text-base font-bold text-on-accent hover:bg-accent-deep disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </>
  )
}
