import { motion } from 'motion/react'
import type { ComponentProps } from 'react'

type IconButtonProps = ComponentProps<typeof motion.button> & { label: string }

/** A round icon-only button, 48 px square. `label` is what a screen reader says. */
export function IconButton({ label, className = '', disabled, ...props }: IconButtonProps) {
  return (
    <motion.button
      aria-label={label}
      title={label}
      whileTap={disabled ? undefined : { scale: 0.9 }}
      disabled={disabled}
      className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-ink transition-colors hover:bg-tile disabled:opacity-40 ${className}`}
      {...props}
    />
  )
}
