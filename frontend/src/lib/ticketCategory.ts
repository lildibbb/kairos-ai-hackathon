type CategoryInfo = { label: string; meaning: string }

const CATEGORIES: Record<string, CategoryInfo> = {
  CPE_REBOOT_LOOP: { label: 'Router keeps restarting', meaning: 'The home router (CPE) is stuck in a reboot loop.' },
  DEVICE_OFFLINE: { label: 'Device offline', meaning: 'A device on the service path stopped responding.' },
  ONU_OFFLINE: { label: 'Fibre modem offline', meaning: 'The ONU (fibre modem) lost its link to the network.' },
  OPTICAL_LOSS: { label: 'No fibre signal', meaning: 'No optical signal is reaching the customer premises.' },
  OPTICAL_DEGRADE: { label: 'Weak fibre signal', meaning: 'Optical power is below the healthy range.' },
  HSI_DEGRADED: { label: 'Slow internet', meaning: 'High-speed internet throughput is degraded.' },
  DNS_RESOLUTION_FAILURE: { label: 'Websites not loading', meaning: 'DNS lookups are failing, so sites will not resolve.' },
  IPTV_STREAM_DEGRADED: { label: 'TV stream issues', meaning: 'The IPTV stream is buffering or dropping.' },
  VOBB_REGISTRATION_FAILED: { label: 'Home phone not working', meaning: 'The voice line failed to register.' },
  WIFI_INTERFERENCE: { label: 'Wi-Fi interference', meaning: 'Nearby networks are crowding the Wi-Fi channel.' },
  CUSTOMER_NO_INTERNET: { label: 'No internet (customer report)', meaning: 'The customer reported having no connection.' },
  CUSTOMER_SLOW_INTERNET: { label: 'Slow internet (customer report)', meaning: 'The customer reported slow speeds.' },
  CUSTOMER_DISCONNECTING: { label: 'Connection drops (customer report)', meaning: 'The customer reported the line dropping in and out.' },
  CUSTOMER_IPTV: { label: 'TV problem (customer report)', meaning: 'The customer reported an IPTV problem.' },
  CUSTOMER_VOICE: { label: 'Phone problem (customer report)', meaning: 'The customer reported a home phone problem.' },
  CUSTOMER_REPORT: { label: 'Customer report', meaning: 'Raised from a customer conversation.' },
}

/** Falls back to sentence case for codes this map does not know yet. */
export function categoryInfo(code: string): CategoryInfo {
  const known = CATEGORIES[code.toUpperCase()]
  if (known) return known
  const words = code.toLowerCase().split('_').join(' ')
  return { label: words.charAt(0).toUpperCase() + words.slice(1), meaning: '' }
}

/** Swaps a leading event code in a ticket summary for its readable label. */
export function readableSummary(summary: string): string {
  return summary.replace(/\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g, (code) => categoryInfo(code).label)
}
