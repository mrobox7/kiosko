/** The mark beside every dish on an Indian menu: a green dot in a green square for vegetarian, a
 * red triangle in a red square for non-vegetarian. The shapes differ as well as the colours, so
 * the two are told apart at a glance and by anyone who cannot tell green from red. */
export function VegMark({ veg, small = false }: { veg: string; small?: boolean }) {
  const isVeg = veg === 'veg'
  const box = small ? 'h-4 w-4 rounded-[3px] border-[1.5px]' : 'h-5 w-5 rounded-[4px] border-2'
  const inner = small ? 'h-2 w-2' : 'h-2.5 w-2.5'
  const triangle = small ? 'h-2.5 w-2.5' : 'h-3 w-3' // a triangle looks smaller than a circle of the same size
  return (
    <span
      role="img"
      aria-label={isVeg ? 'Vegetarian' : 'Non-vegetarian'}
      className={`inline-flex shrink-0 items-center justify-center bg-white ${box} ${isVeg ? 'border-veg text-veg' : 'border-nonveg text-nonveg'}`}
    >
      {isVeg ? (
        <span className={`rounded-full bg-current ${inner}`} />
      ) : (
        <svg viewBox="0 0 10 10" aria-hidden className={`fill-current ${triangle}`}>
          <path d="M5 .5 10 9.5H0z" />
        </svg>
      )}
    </span>
  )
}
