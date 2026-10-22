import type { VoiceState } from '../../voice/useVoice'

const labels: Record<VoiceState, string> = {
  idle: 'Listening…',
  recording: 'Recording…',
  listening: 'Listening… go ahead, just talk',
  hearing: 'Hearing you…',
  working: 'Thinking…',
  speaking: 'Speaking… talk over me to interrupt',
}

function HeadsetIcon({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 3a9 9 0 0 0-9 9v7a3 3 0 0 0 3 3h1a1 1 0 0 0 1-1v-6a1 1 0 0 0-1-1H5v-2a7 7 0 0 1 14 0v2h-3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h1a3 3 0 0 0 3-3v-7a9 9 0 0 0-9-9z" />
    </svg>
  )
}

/** The orb that shows what the voice chat is doing. */
function Orb({ state }: { state: VoiceState }) {
  const hearing = state === 'hearing'
  const speaking = state === 'speaking'
  const working = state === 'working'
  return (
    <div className="relative flex h-12 w-12 shrink-0 items-center justify-center">
      {(state === 'listening' || hearing) && (
        <span className={'absolute inset-0 animate-ping rounded-full ' + (hearing ? 'bg-promo/60' : 'bg-accent/50')} />
      )}
      <span
        className={
          'relative flex h-12 w-12 items-center justify-center rounded-full text-on-accent shadow-md transition-colors ' +
          (hearing ? 'bg-promo text-white' : speaking ? 'bg-accent-deep' : 'bg-accent')
        }
      >
        {speaking ? (
          <span className="flex h-5 items-end gap-[3px]">
            {[0, 150, 300, 450].map((delay) => (
              <span key={delay} className="w-[3px] animate-bounce rounded-full bg-on-accent" style={{ height: '100%', animationDelay: `${delay}ms` }} />
            ))}
          </span>
        ) : working ? (
          <span className="h-5 w-5 animate-spin rounded-full border-2 border-black/30 border-t-black" />
        ) : (
          <HeadsetIcon />
        )}
      </span>
    </div>
  )
}

/**
 * The voice chat control. Off, it is a plain call to action; on, it shows what is going on.
 * Push-to-talk (the small mic by the text box) is separate.
 */
export function VoiceDock({
  state,
  handsFree,
  onToggle,
}: {
  state: VoiceState
  handsFree: boolean
  onToggle: () => void
}) {
  if (handsFree) {
    return (
      <div role="status" aria-live="polite" className="mx-3 mb-2 flex items-center gap-4 rounded-2xl bg-accent-soft p-3 ring-1 ring-accent md:mx-4">
        <Orb state={state} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">Voice chat is on</p>
          <p className="truncate text-sm text-muted">{labels[state]}</p>
        </div>
        <button
          onClick={onToggle}
          className="shrink-0 rounded-(--radius-key) bg-promo px-4 py-2 text-sm font-bold text-white shadow-sm hover:brightness-110"
        >
          End
        </button>
      </div>
    )
  }
  const busy = state !== 'idle'
  return (
    <button
      onClick={onToggle}
      disabled={busy}
      className="mx-3 mb-2 flex items-center gap-4 rounded-2xl bg-accent p-3 text-left text-on-accent shadow-md transition hover:bg-accent-deep disabled:opacity-50 md:mx-4"
    >
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-black/10">
        <HeadsetIcon />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-base font-semibold">Start voice chat</span>
        <span className="hidden text-sm sm:block">Talk hands-free. Just speak, and speak over me to interrupt.</span>
      </span>
      <span className="shrink-0 rounded-xl bg-on-accent px-4 py-2 text-sm font-bold text-accent">Talk</span>
    </button>
  )
}
