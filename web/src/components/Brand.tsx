import { Logo } from './Logo'

/** The logo with the outlet's name beside it. */
export function Brand({ name }: { name: string }) {
  return (
    <div className="flex items-end gap-3">
      <Logo />
      <span className="hidden pb-0.5 text-sm leading-none font-semibold text-muted landscape:md:inline">{name}</span>
    </div>
  )
}
