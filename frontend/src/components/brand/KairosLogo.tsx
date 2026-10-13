type KairosLogoProps = { className?: string; descriptor?: string; tone?: 'light' | 'dark' }

export function KairosLogo({ className = '', descriptor, tone = 'dark' }: KairosLogoProps) {
  return (
    <span className={`kairos-logo kairos-logo--${tone} ${className}`}>
      <img className="kairos-logo__mark" src="/brand/kairos-mark.svg" alt="" width="32" height="32" />
      <span className="kairos-logo__word">Kairos<sup className="kairos-logo__tm" aria-label="trademark">TM</sup></span>
      <span className="kairos-logo__divider" aria-hidden="true" />
      <img className="kairos-logo__partner" src="/brand/tm-logo.svg" alt="Telekom Malaysia" width="56" height="28" />
      {descriptor && <span className="brand-descriptor">{descriptor}</span>}
    </span>
  )
}
