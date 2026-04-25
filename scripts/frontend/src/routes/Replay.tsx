import { Panel } from '@/components/chrome/Panel'

export function Replay(): React.ReactElement {
  return (
    <div className="h-full p-4">
      <Panel title="REPLAY">
        <p className="font-mono text-text-mid">
          Historical replay scrubber coming in Phase 3. Backend history
          collection is active now (90-day retention) — UI for it follows.
        </p>
      </Panel>
    </div>
  )
}
