/** What the agent is doing right now; the topology animates from this. */
export type AgentPhase = 'thinking' | 'planning' | 'awaiting' | 'executing' | 'verifying' | 'succeeded' | 'failed'

export type AgentActivity = {
  phase: AgentPhase
  label: string
  deviceId?: string
  toolName?: string
  toolKind?: 'read_only' | 'stateful'
  /** The live trace step being replayed, e.g. "Sweep 2.4 GHz". */
  step?: string
  /** Devices the current step touches (path hops, surveyed or steered clients). */
  focusIds?: string[]
  /** Short readings pinned to devices on the canvas, e.g. { deviceId: "-82 dBm" }. */
  metrics?: Record<string, { text: string; tone: 'ok' | 'warn' | 'bad' }>
  /** 0-1 progress through the replayed trace. */
  progress?: number
}

export type AgentActivityReporter = (activity: AgentActivity | null) => void

export const AGENT_PHASE_LABEL: Record<AgentPhase, string> = {
  thinking: 'Reading the network',
  planning: 'Planning a tool call',
  awaiting: 'Awaiting your approval',
  executing: 'Executing on device',
  verifying: 'Verifying device state',
  succeeded: 'Action completed',
  failed: 'Action failed',
}

export function wait(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms))
}

/** Tool parameters as a short call signature, e.g. set_wifi_channel(band=2.4, channel=6). */
export function toolSignature(toolName: string, parameters: Record<string, unknown>) {
  const args = Object.entries(parameters)
    .filter(([key]) => key !== 'device_id')
    .map(([key, value]) => `${key}=${typeof value === 'object' && value !== null ? Object.entries(value).map(([k, v]) => `${k}:${String(v)}`).join(',') : String(value)}`)
  return `${toolName}(${args.join(', ')})`
}
