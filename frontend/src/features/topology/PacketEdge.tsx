import type { CSSProperties } from 'react'
import { BaseEdge, getStraightPath, type EdgeProps, type Edge } from '@xyflow/react'
import './packet-stream.css'

type PacketData = {
  broken: boolean
  paused: boolean
  active: boolean
  /** Agent command traffic: 'in' flows toward the edge target, 'out' away from the source. */
  command?: 'in' | 'out'
  tone?: 'agent' | 'ok' | 'fail'
}

const COMMAND_FILL = { agent: '#a99cff', ok: '#5fe0b0', fail: '#f08a7e' }

/** Radius of the device circle; links start and end on its rim, not its centre. */
export const DEVICE_RADIUS = 31

/** Shorten a centre-to-centre segment so it touches both device circles. */
export function trimToRims(sx: number, sy: number, tx: number, ty: number, radius = DEVICE_RADIUS) {
  const dx = tx - sx
  const dy = ty - sy
  const length = Math.hypot(dx, dy)
  if (length <= radius * 2 + 4) return { sourceX: sx, sourceY: sy, targetX: tx, targetY: ty }
  const ux = dx / length
  const uy = dy / length
  return { sourceX: sx + ux * radius, sourceY: sy + uy * radius, targetX: tx - ux * radius, targetY: ty - uy * radius }
}

export function PacketEdge({ id, sourceX: rawSourceX, sourceY: rawSourceY, targetX: rawTargetX, targetY: rawTargetY, style, data, label, labelStyle, labelBgStyle, labelBgPadding }: EdgeProps<Edge<PacketData>>) {
  const { sourceX, sourceY, targetX, targetY } = trimToRims(rawSourceX, rawSourceY, rawTargetX, rawTargetY)
  const [path, labelX, labelY] = getStraightPath({ sourceX, sourceY, targetX, targetY })
  const labelProps = { label, labelX, labelY, labelStyle, labelBgStyle, labelBgPadding, labelShowBg: Boolean(label) }
  const active = data?.active ?? false
  const angle = Math.atan2(targetY - sourceY, targetX - sourceX) * 180 / Math.PI
  const packetStyle = (index: number, reverse: boolean, spacing = 0.93): CSSProperties => ({
    '--packet-from': `translate(${reverse ? targetX : sourceX}px, ${reverse ? targetY : sourceY}px)`,
    '--packet-to': `translate(${reverse ? sourceX : targetX}px, ${reverse ? sourceY : targetY}px)`,
    animationDelay: `${-index * spacing - (reverse ? 0.46 : 0)}s`,
    animationPlayState: data?.paused ? 'paused' : 'running',
  } as CSSProperties)

  if (data?.command && !data.broken) {
    const fill = COMMAND_FILL[data.tone ?? 'agent']
    return <>
      <BaseEdge id={id} path={path} style={style} {...labelProps} />
      <path d={path} className="network-stream__glow" stroke={fill} aria-hidden="true" />
      <g className="network-stream network-stream--command" aria-hidden="true" style={{ pointerEvents: 'none' }}>
        {[0, 1, 2, 3, 4].map((index) => (
          <g key={index} className="network-stream__packet network-stream__packet--command" style={packetStyle(index, false, 0.24)}>
            <circle r="4" fill={fill} />
            <circle r="8" fill={fill} opacity="0.25" />
          </g>
        ))}
      </g>
    </>
  }

  return <>
    <BaseEdge id={id} path={path} style={style} {...labelProps} />
    {!data?.broken && <g className="network-stream" aria-hidden="true" style={{ pointerEvents: 'none' }}>
      {[false, true].flatMap((reverse) => [0, 1, 2].map((index) => (
        <g key={`${reverse}-${index}`} className="network-stream__packet" style={packetStyle(index, reverse)}>
          <rect x="-6" y={reverse ? -5 : 2} width={active ? 15 : 11} height="3" rx="1.5"
            transform={`rotate(${angle})`} fill={active ? '#80531d' : reverse ? '#526b87' : '#28664e'} />
        </g>
      )))}
    </g>}
  </>
}
