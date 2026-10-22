/** "Veg only", as a switch: the track slides and turns green. */
export function VegSwitch({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={onToggle}
      className="flex min-h-9 items-center gap-2 rounded-(--radius-key) bg-tile px-3 text-xs font-semibold"
    >
      Veg only
      <span className={`relative h-5 w-9 rounded-full transition-colors ${on ? 'bg-veg' : 'bg-line'}`}>
        <span className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${on ? 'translate-x-4' : ''}`} />
      </span>
    </button>
  )
}
