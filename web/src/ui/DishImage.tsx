import { useState } from 'react'

/** A dish's picture, or a plain tile with its first letter when it has none or fails to load. */
export function DishImage({ src, name, className = '' }: { src: string | null; name: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  if (!src || failed) {
    return (
      <div
        aria-hidden
        className={`flex items-center justify-center bg-tile text-5xl font-black text-accent ${className}`}
      >
        {name.trim()[0]?.toUpperCase()}
      </div>
    )
  }
  return (
    <img src={src} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} className={`object-contain ${className}`} />
  )
}
