import { motion } from 'motion/react'
import type { ComponentProps } from 'react'

const looks = {
  primary: 'bg-accent text-on-accent hover:bg-accent-deep',
  soft: 'bg-tile text-ink hover:bg-line',
  promo: 'bg-promo text-white hover:brightness-110',
  quiet: 'text-muted hover:bg-tile',
}

const sizes = {
  md: 'min-h-12 px-6 text-sm',
  lg: 'min-h-16 px-8 text-base',
}

type ButtonProps = ComponentProps<typeof motion.button> & {
  look?: keyof typeof looks
  size?: keyof typeof sizes
}

/** A touch button, a rounded square like the reference's: at least 48 px tall, presses in a
 * little when tapped. */
export function Button({ look = 'primary', size = 'md', className = '', disabled, ...props }: ButtonProps) {
  return (
    <motion.button
      whileTap={disabled ? undefined : { scale: 0.96 }}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-(--radius-key) whitespace-nowrap font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${looks[look]} ${sizes[size]} ${className}`}
      {...props}
    />
  )
}
