function initials(name: string) {
  const words = name.trim().split(/\s+/).filter(Boolean)
  return ((words[0]?.[0] ?? '') + (words.length > 1 ? words[words.length - 1][0] : '')).toUpperCase() || '?'
}

/** The round picture before a message: the DishPatch badge, or the customer's initials. */
export function Avatar({ who, name = '' }: { who: 'assistant' | 'user'; name?: string }) {
  if (who === 'assistant') {
    return (
      <div
        aria-hidden
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-on-accent shadow-sm"
      >
        <svg width={18} height={18} viewBox="0 0 24 24" fill="currentColor">
          <path d="M7 2v8a2 2 0 0 0 1.5 1.94V22h2V11.94A2 2 0 0 0 12 10V2h-1.5v6H9.25V2h-1.5v6H8.5V2H7zm9 0c-1.66 0-3 2.24-3 5s1.34 5 3 5v10h2V2h-2z" />
        </svg>
      </div>
    )
  }
  return (
    <div
      aria-hidden
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-xs font-semibold text-page shadow-sm"
    >
      {initials(name)}
    </div>
  )
}
