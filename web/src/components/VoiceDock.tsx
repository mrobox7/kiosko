import type { VoiceState } from '../voice/useVoice'

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
        <span className={'absolute inset-0 animate-ping rounded-full ' + (hearing ? 'bg-red-400/60' : 'bg-amber-400/50')} />
      )}
      <span
        className={
          'relative flex h-12 w-12 items-center justify-center rounded-full text-white shadow-md transition-colors ' +
          (hearing ? 'bg-red-600' : speaking ? 'bg-amber-800' : 'bg-amber-700')
        }
      >
        {speaking ? (
          <span className="flex h-5 items-end gap-[3px]">
            {[0, 150, 300, 450].map((delay) => (
              <span key={delay} className="w-[3px] animate-bounce rounded-full bg-white" style={{ height: '100%', animationDelay: `${delay}ms` }} />
            ))}
          </span>
        ) : working ? (
          <span className="h-5 w-5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
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
      <div role="status" aria-live="polite" className="mx-3 mb-2 flex items-center gap-4 rounded-2xl bg-amber-50 p-3 ring-1 ring-amber-200 md:mx-4">
        <Orb state={state} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-amber-900">Voice chat is on</p>
          <p className="truncate text-sm text-amber-800">{labels[state]}</p>
        </div>
        <button
          onClick={onToggle}
          className="shrink-0 rounded-full bg-red-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-red-700"
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
      className="mx-3 mb-2 flex items-center gap-4 rounded-2xl bg-amber-700 p-3 text-left text-white shadow-md transition hover:bg-amber-800 disabled:opacity-50 md:mx-4"
    >
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white/20">
        <HeadsetIcon />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-base font-semibold">Start voice chat</span>
        <span className="hidden text-sm text-amber-100 sm:block">Talk hands-free. Just speak, and speak over me to interrupt.</span>
      </span>
      <span className="shrink-0 rounded-full bg-white px-4 py-2 text-sm font-semibold text-amber-800">Talk</span>
    </button>
  )
}
