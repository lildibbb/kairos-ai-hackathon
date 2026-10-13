import type { ToolExecution } from '../../lib/api/tools'
import { Button } from '../../components/ui/button'
import { motion, useReducedMotion } from 'framer-motion'
import { reveal, settle } from '../../lib/motion'
import { ToolCall } from '../../components/ai/tool-call'
import { ToolResultView } from './ToolResultView'

type ToolExecutionResultProps = {
  execution: ToolExecution
  onRunAnother?: () => void
  runAnotherLabel?: string
  /** Read-only checks report a reading, not an applied change. */
  readOnly?: boolean
  expandResult?: boolean
  onSelectDevice?: (deviceId: string) => void
}

export function ToolExecutionResult({ execution, onRunAnother, onSelectDevice, runAnotherLabel = 'Prepare another action', readOnly = false, expandResult = false }: ToolExecutionResultProps) {
  const reducedMotion = Boolean(useReducedMotion())
  const succeeded = execution.status === 'succeeded'
  return (
    <motion.div className={`execution-result ${succeeded ? 'is-success' : 'is-failure'}`} role="status" aria-live="polite"
      variants={succeeded ? settle : reveal} initial="hidden" animate="visible" custom={reducedMotion}>
      <ToolCall title="Execution result" status={succeeded ? 'completed' : 'failed'} correlationId={execution.correlation_id}>
      <p className={`execution-status ${succeeded ? 'is-success' : 'is-failure'}`}>
        <span aria-hidden="true">{succeeded ? 'OK' : 'FAILED'}</span>{' '}
         {succeeded ? (readOnly ? 'Check completed' : 'Change applied, verification pending') : 'Action failed'}
      </p>
       <p>{execution.message}</p>
       {execution.result && <details className="execution-result__data" open={expandResult}><summary>Device result</summary><ToolResultView result={execution.result} /></details>}
       {succeeded && !readOnly && <p className="execution-verification-note">This confirms the tool result only. It does not confirm that the customer issue is resolved.</p>}
      <dl className="proposal-details">
        <div>
          <dt>Device</dt>
          <dd>{execution.device_ref}</dd>
        </div>
        <div>
          <dt>Action</dt>
          <dd>{execution.tool_name}</dd>
        </div>
        <div>
          <dt>Recorded</dt>
          <dd>{new Date(execution.executed_at).toLocaleString()}</dd>
        </div>
      </dl>
      {onSelectDevice && <Button variant="quiet" type="button" onClick={() => onSelectDevice(execution.device_id)}>
        Show {execution.device_ref} in topology
      </Button>}
      {onRunAnother && <Button className="text-button" variant="quiet" type="button" onClick={onRunAnother}>
        {runAnotherLabel}
      </Button>}
      </ToolCall>
    </motion.div>
  )
}
