type Tone = 'blue' | 'orange' | 'slate' | 'white'
type Box = { x: number; y: number; z: number; w: number; d: number; h: number; tone: Tone; float?: 0 | 1 | 2 }
type Variant = 'network' | 'signal' | 'stack' | 'tower' | 'devices' | 'resolved'

// Isometric boxes in world units, projected to SVG; motion is CSS transform/opacity on <g>, so it stays cheap.
const SCENES: Record<Variant, Box[]> = {
  network: [
    { x: -62, y: 0, z: 0, w: 34, d: 34, h: 16, tone: 'white' },
    { x: 62, y: 0, z: 0, w: 34, d: 34, h: 16, tone: 'white' },
    { x: 0, y: -62, z: 0, w: 34, d: 34, h: 16, tone: 'white' },
    { x: 0, y: 0, z: 0, w: 46, d: 46, h: 34, tone: 'blue' },
    { x: 0, y: 0, z: 54, w: 16, d: 16, h: 16, tone: 'orange', float: 1 },
  ],
  signal: [
    { x: 0, y: 0, z: 0, w: 74, d: 46, h: 16, tone: 'white' },
    { x: -24, y: 10, z: 16, w: 7, d: 7, h: 40, tone: 'slate' },
    { x: 24, y: 10, z: 16, w: 7, d: 7, h: 40, tone: 'slate' },
    { x: 0, y: 0, z: 74, w: 14, d: 14, h: 14, tone: 'orange', float: 1 },
  ],
  stack: [
    { x: 0, y: 0, z: 0, w: 58, d: 58, h: 16, tone: 'slate' },
    { x: 0, y: 0, z: 22, w: 58, d: 58, h: 16, tone: 'white', float: 0 },
    { x: 0, y: 0, z: 44, w: 58, d: 58, h: 16, tone: 'blue', float: 1 },
    { x: 0, y: 0, z: 82, w: 14, d: 14, h: 14, tone: 'orange', float: 2 },
  ],
  tower: [
    { x: 0, y: 0, z: 0, w: 54, d: 54, h: 10, tone: 'white' },
    { x: 0, y: 0, z: 10, w: 12, d: 12, h: 82, tone: 'slate' },
    { x: 0, y: 0, z: 70, w: 30, d: 8, h: 14, tone: 'blue' },
    { x: 0, y: 0, z: 104, w: 12, d: 12, h: 12, tone: 'orange', float: 1 },
  ],
  devices: [
    { x: -40, y: 20, z: 0, w: 60, d: 40, h: 10, tone: 'white' },
    { x: -40, y: 20, z: 10, w: 52, d: 4, h: 34, tone: 'slate' },
    { x: 40, y: -10, z: 0, w: 20, d: 34, h: 6, tone: 'blue', float: 0 },
    { x: 26, y: 46, z: 0, w: 22, d: 22, h: 22, tone: 'white', float: 2 },
    { x: 0, y: 0, z: 62, w: 12, d: 12, h: 12, tone: 'orange', float: 1 },
  ],
  resolved: [
    { x: 0, y: 0, z: 0, w: 70, d: 70, h: 12, tone: 'white' },
    { x: 0, y: 0, z: 12, w: 40, d: 40, h: 26, tone: 'blue', float: 0 },
    { x: -46, y: 30, z: 40, w: 9, d: 9, h: 9, tone: 'orange', float: 1 },
    { x: 42, y: -34, z: 52, w: 7, d: 7, h: 7, tone: 'orange', float: 2 },
  ],
}

const COLORS: Record<Tone, [string, string, string]> = {
  white: ['#ffffff', '#e2e8f0', '#cbd5e1'],
  slate: ['#64748b', '#475569', '#334155'],
  blue: ['#2563c9', '#003da5', '#002a73'],
  orange: ['#ff9a5c', '#f37021', '#c2530f'],
}

const C = Math.cos(Math.PI / 6)
const project = (x: number, y: number, z: number) => [(x - y) * C, (x + y) * 0.5 - z] as const
const pts = (list: (readonly [number, number])[]) => list.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(' ')

function Prism({ box }: { box: Box }) {
  const { x, y, z, w, d, h, tone, float } = box
  const [x0, x1, y0, y1] = [x - w / 2, x + w / 2, y - d / 2, y + d / 2]
  const top = pts([project(x0, y0, z + h), project(x1, y0, z + h), project(x1, y1, z + h), project(x0, y1, z + h)])
  const left = pts([project(x0, y1, z + h), project(x1, y1, z + h), project(x1, y1, z), project(x0, y1, z)])
  const right = pts([project(x1, y0, z + h), project(x1, y1, z + h), project(x1, y1, z), project(x1, y0, z)])
  const [t, r, l] = COLORS[tone]
  return (
    <g className={float === undefined ? undefined : `s3d-float s3d-float--${float}`}>
      <polygon points={left} fill={l} /><polygon points={right} fill={r} /><polygon points={top} fill={t} />
    </g>
  )
}

const depth = (b: Box) => b.x + b.y + b.z * 0.01

export function Scene3D({ variant = 'network', size = 220, className = '' }: { variant?: Variant; size?: number; className?: string }) {
  const boxes = [...SCENES[variant]].sort((a, b) => (a.z === b.z ? depth(a) - depth(b) : a.z - b.z))
  const [hubX, hubY] = project(0, 0, 0)
  return (
    <svg className={`s3d s3d--${variant} ${className}`} width={size} height={size * 0.8} viewBox="-120 -130 240 192" aria-hidden="true" focusable="false">
      <ellipse className="s3d-shadow" cx={hubX} cy={hubY + 14} rx="96" ry="40" />
      {variant === 'network' && [[-62, 0], [62, 0], [0, -62]].map(([lx, ly]) => {
        const [ax, ay] = project(lx, ly, 2); const [bx, by] = project(0, 0, 2)
        return <g key={`${lx}${ly}`}><line x1={ax} y1={ay} x2={bx} y2={by} className="s3d-cable" /><line x1={ax} y1={ay} x2={bx} y2={by} className="s3d-packet" /></g>
      })}
      <g className="s3d-scene">{boxes.map((box, i) => <Prism key={i} box={box} />)}</g>
      {(variant === 'signal' || variant === 'tower') && [0, 1, 2].map((i) => {
        const [cx, cy] = project(0, 0, variant === 'tower' ? 110 : 80)
        return <ellipse key={i} className="s3d-ring" style={{ animationDelay: `${i * 0.9}s` }} cx={cx} cy={cy} rx="34" ry="17" />
      })}
      {variant === 'resolved' && <path className="s3d-check" d="M-13 -40 l9 8 l18 -18" />}
    </svg>
  )
}
