import { MinusIcon, PlusIcon } from './Icons'

const tones = {
  normal: { minus: 'bg-tile text-ink', plus: 'bg-accent text-on-accent', count: 'text-ink' },
  onGreen: { minus: 'bg-black/20 text-white', plus: 'bg-white text-review', count: 'text-white' },
}

/** − 2 +. Small, as in the reference: 32 px buttons; one is disabled at its limit. The plus is the accent, as in the
 * reference. `onGreen` is for the order review screen. */
export function Stepper({
  value,
  min,
  max,
  label,
  tone = 'normal',
  onChange,
}: {
  value: number
  min: number
  max: number
  label: string // what is being counted, for screen readers
  tone?: keyof typeof tones
  onChange: (value: number) => void
}) {
  const look = tones[tone]
  const button = 'flex h-8 w-8 items-center justify-center rounded-lg transition active:scale-90 disabled:opacity-30'
  return (
    <div className="inline-flex items-center gap-1" role="group" aria-label={label}>
      <button type="button" aria-label={`Fewer ${label}`} className={`${button} ${look.minus}`} disabled={value <= min} onClick={() => onChange(value - 1)}>
        <MinusIcon width={16} height={16} />
      </button>
      <span className={`min-w-7 text-center text-sm font-semibold tabular-nums ${look.count}`} aria-live="polite">
        {value}
      </span>
      <button type="button" aria-label={`More ${label}`} className={`${button} ${look.plus}`} disabled={value >= max} onClick={() => onChange(value + 1)}>
        <PlusIcon width={16} height={16} />
      </button>
    </div>
  )
}
