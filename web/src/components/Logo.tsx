/** The logo, from `public/logo.png`. Swap the file to change it. */
export function Logo({ className = 'h-10' }: { className?: string }) {
  return <img src="/logo.png" alt="McDonald's" className={`w-auto ${className}`} />
}
