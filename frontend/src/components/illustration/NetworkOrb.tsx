type NetworkOrbProps = { className?: string; variant?: 'hero' | 'compact' }

export function NetworkOrb({ className = '', variant = 'hero' }: NetworkOrbProps) {
  return <img className={`network-illustration network-illustration--${variant} ${className}`} src="/illustrations/network-studio.svg" alt="Isometric network equipment connected by an amber fiber cable" width="960" height="660" />
}
