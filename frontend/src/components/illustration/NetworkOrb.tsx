import { useLayoutEffect, useRef } from 'react'
import { gsap } from 'gsap'
import { prefersReducedMotion } from '../../lib/motion'

type NetworkOrbProps = {
  className?: string
  variant?: 'hero' | 'compact'
}

export function NetworkOrb({ className = '', variant = 'hero' }: NetworkOrbProps) {
  const rootRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root || prefersReducedMotion()) return
    const context = gsap.context(() => {
      gsap.fromTo(
        '.network-orb__plane',
        { opacity: 0, scale: 0.88, rotateX: 48, rotateZ: -18 },
        { opacity: 1, scale: 1, rotateX: 58, rotateZ: -22, duration: 0.9, ease: 'power3.out' },
      )
      gsap.fromTo(
        '.network-orb__node',
        { opacity: 0, scale: 0.4 },
        { opacity: 1, scale: 1, duration: 0.4, delay: 0.3, stagger: 0.08, ease: 'back.out(1.8)' },
      )
      gsap.to('.network-orb__float', {
        y: -10,
        duration: 2.6,
        ease: 'sine.inOut',
        repeat: -1,
        yoyo: true,
        stagger: 0.3,
      })
      gsap.to('.network-orb__ring--outer', {
        rotateZ: '+=360',
        duration: 28,
        ease: 'none',
        repeat: -1,
      })
      gsap.to('.network-orb__ring--inner', {
        rotateZ: '-=360',
        duration: 20,
        ease: 'none',
        repeat: -1,
      })
    }, root)
    return () => context.revert()
  }, [])

  return (
    <div
      ref={rootRef}
      className={`network-orb network-orb--${variant} ${className}`}
      role="img"
      aria-label="Abstract network signal visualization"
    >
      <div className="network-orb__plane network-orb__float">
        <span className="network-orb__ring network-orb__ring--outer" />
        <span className="network-orb__ring network-orb__ring--inner" />
        <span className="network-orb__core" />
        <span className="network-orb__node network-orb__node--one" />
        <span className="network-orb__node network-orb__node--two" />
        <span className="network-orb__node network-orb__node--three" />
        <span className="network-orb__beam network-orb__beam--one" />
        <span className="network-orb__beam network-orb__beam--two" />
      </div>
    </div>
  )
}
