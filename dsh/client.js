// ARIS run status — browser half.
//
// One read-only conversation tab showing what the independent reviewer and the
// loop's own artifacts say. It never writes, never advances a round, and never
// converts a score, verdict, or `completed` status into a completion decision:
// a loop can DRIVE but cannot ACQUIT, and neither can a dashboard.
//
// Handwritten on purpose — the file is small and fixed, so the package stays
// build-free. A second view or any interactive mutation should move this to a
// normal source-and-build setup instead of growing here.

window.__ModuleLoader__.load({
  id: 'dsh-aris',
  factory(require) {
    const React = require('react')
    const h = React.createElement

    const POLL_MS = 5000

    /** Fields that answer "is the reviewer genuinely independent right now". */
    const INDEPENDENCE = [
      ['Executor', s => label(s.executor_model, s.executor_family)],
      ['Reviewer', s => label(s.reported_reviewer_model ?? s.requested_reviewer_model, s.reviewer_family)],
      ['Families', s => s.family_relation],
      ['Independence verified', s => format(s.independence_verified)],
      ['External acquittal owed', s => format(s.requires_external_acquittal)],
    ]

    /** Fields describing where the loop stands. */
    const PROGRESS = [
      ['Round', s => s.round === undefined ? undefined : `Round ${s.round}`],
      ['Loop status', s => s.status === 'completed' ? 'ended (positive assessment or max rounds)' : s.status],
      ['Difficulty', s => s.difficulty],
      ['Reviewer backend (next round)', s => s.reviewer_backend],
      ['Last score', s => s.last_score === undefined ? undefined : String(s.last_score)],
      ['Last verdict', s => s.last_verdict],
      ['Run id', s => s.run_id],
    ]

    function label(model, family) {
      if (model === undefined || model === null) return family
      return family === undefined || family === null ? String(model) : `${model} (${family})`
    }

    function format(value) {
      if (value === true) return 'yes'
      if (value === false) return 'no'
      return value === undefined || value === null ? undefined : String(value)
    }

    function when(ms) {
      if (typeof ms !== 'number') return ''
      const seconds = Math.max(0, Math.round((Date.now() - ms) / 1000))
      if (seconds < 90) return `${seconds}s ago`
      const minutes = Math.round(seconds / 60)
      return minutes < 90 ? `${minutes}m ago` : `${Math.round(minutes / 60)}h ago`
    }

    function rows(spec, state) {
      const present = []
      for (const [name, read] of spec) {
        let value
        try {
          value = read(state)
        } catch {
          value = undefined
        }
        if (value !== undefined && value !== null && value !== '') {
          present.push(h('div', { className: 'aris-row', key: name },
            h('span', { className: 'aris-key' }, name),
            h('span', { className: 'aris-value' }, String(value))))
        }
      }
      return present
    }

    function Section(props) {
      return h('section', { className: 'aris-section' },
        h('h3', null, props.title),
        props.children)
    }

    /**
     * One pipeline phase. `accepted` is the only status an independent reviewer
     * can produce; `done` is the executor's own claim, so a done-but-unaccepted
     * phase is shown as the open acceptance obligation it is.
     */
    function Phase(props) {
      const p = props.phase
      const accepted = p.status === 'accepted'
      const owed = p.status === 'done'
      const detail = accepted
        ? [p.reviewer, p.reviewerFamily && `(${p.reviewerFamily})`, p.independence]
          .filter(Boolean).join(' ')
        : owed ? 'executor self-report — not yet accepted by a reviewer' : undefined
      return h('div', { className: 'aris-phase' },
        h('span', { className: 'aris-phase-name' }, p.phase),
        h('span', { className: 'aris-phase-status aris-status-' + p.status }, p.status),
        h('span', { className: 'aris-phase-detail' },
          detail,
          p.artifact === undefined ? null : h('code', { className: 'aris-phase-artifact' }, p.artifact)))
    }

    function ArisRunView(props) {
      const [data, setData] = React.useState(undefined)
      const [error, setError] = React.useState(undefined)
      const connection = props.connection

      React.useEffect(() => {
        let live = true
        const controller = new AbortController()
        const poll = () => {
          connection.rpc.call('/aris', 'state', { sessionId: props.sessionId }, controller.signal)
            .then((result) => {
              if (!live) return
              if (result.ok) {
                setData(result.value)
                setError(undefined)
              } else {
                setError(result.error && result.error.message ? result.error.message : 'RPC failed')
              }
            })
            .catch((cause) => { if (live) setError(String(cause)) })
        }
        poll()
        const timer = setInterval(poll, POLL_MS)
        return () => { live = false; clearInterval(timer); controller.abort() }
      }, [connection, props.sessionId])

      if (error !== undefined) {
        return h('div', { className: 'aris-view' }, h('p', { className: 'aris-note' }, error))
      }
      if (data === undefined) {
        return h('div', { className: 'aris-view' }, h('p', { className: 'aris-note' }, 'Reading run artifacts…'))
      }
      if (data.workspace === undefined) {
        return h('div', { className: 'aris-view' },
          h('p', { className: 'aris-note' }, 'This session has no workspace directory, so there are no ARIS artifacts to read.'))
      }

      const state = data.state
      const children = []

      const pipeline = data.pipeline
      const pipelineSection = pipeline === undefined ? undefined : (() => {
        const owed = pipeline.phases.filter(p => p.status === 'done').length
        return h(Section, { title: 'Pipeline', key: 'pipeline' },
          h('p', { className: 'aris-note aris-run' },
            [pipeline.runId, pipeline.updated && `updated ${pipeline.updated}`]
              .filter(Boolean).join(' · ')),
          pipeline.phases.map(p => h(Phase, { phase: p, key: p.phase })),
          h('p', { className: 'aris-note' },
            owed === 0
              ? 'Only "accepted" means an independent reviewer or a deterministic verifier signed off; "done" is the executor\'s own claim.'
              : `${owed} phase${owed === 1 ? '' : 's'} marked done by the executor but never accepted by a reviewer — an open acceptance obligation.`))
      })()

      if (data.stateError !== undefined) {
        children.push(h('p', { className: 'aris-note', key: 'state-error' }, data.stateError))
      } else if (state === undefined) {
        children.push(h('p', { className: 'aris-note', key: 'no-state' },
          'No review-stage/REVIEW_STATE.json yet — no auto-review-loop run has completed a round in this workspace.'))
      } else {
        // Independence leads: it is the property ARIS rests on, and the reason
        // this tab exists at all.
        children.push(h(Section, { title: 'Reviewer independence', key: 'independence' }, rows(INDEPENDENCE, state)))
        if (pipelineSection !== undefined) children.push(pipelineSection)
        children.push(h(Section, { title: 'Loop', key: 'loop' },
          rows(PROGRESS, state),
          data.criticisms === undefined ? null : h('div', { className: 'aris-criticisms' },
            h('div', { className: 'aris-key' }, 'Last assessment'),
            h('ul', { className: 'aris-list' },
              data.criticisms.map((item, index) => h('li', { key: index }, item))))))
        if (Array.isArray(state.pending_experiments) && state.pending_experiments.length > 0) {
          children.push(h(Section, { title: 'Pending experiments', key: 'pending' },
            h('ul', { className: 'aris-list' },
              state.pending_experiments.map((item, index) =>
                h('li', { key: index }, String(item))))))
        }
        children.push(h('p', { className: 'aris-note', key: 'staleness' },
          `State is written when a round finishes, not continuously — this reflects the last completed round${
            state.timestamp === undefined ? '' : ` (recorded ${state.timestamp})`}.`))
      }

      children.push(h(Section, { title: 'Artifacts', key: 'artifacts' },
        h('ul', { className: 'aris-list' }, data.artifacts.map(item =>
          h('li', { key: item.path },
            h('span', { className: item.exists ? 'aris-ok' : 'aris-missing' }, item.exists ? '●' : '○'),
            ' ',
            h('code', null, item.path),
            item.exists ? h('span', { className: 'aris-when' }, ' ' + when(item.mtime)) : null)))))

      if (state === undefined && pipelineSection !== undefined) children.push(pipelineSection)
      children.push(h('p', { className: 'aris-note', key: 'workspace' }, data.workspace))

      return h('div', { className: 'aris-view' }, children)
    }

    const CSS = `
.aris-view { padding: 16px 20px; overflow-y: auto; font-size: 13px; line-height: 1.6; }
.aris-section { margin-bottom: 18px; }
.aris-section h3 { margin: 0 0 6px; font-size: 12px; letter-spacing: .04em; text-transform: uppercase; opacity: .6; font-weight: 600; }
.aris-row { display: flex; gap: 12px; padding: 2px 0; }
.aris-key { flex: 0 0 190px; opacity: .7; }
.aris-value { flex: 1; word-break: break-word; }
.aris-list { margin: 0; padding-left: 18px; }
.aris-list li { padding: 1px 0; }
.aris-note { opacity: .6; font-size: 12px; margin: 8px 0 0; }
.aris-ok { color: #2ea043; }
.aris-missing { opacity: .4; }
.aris-when { opacity: .55; font-size: 12px; }
.aris-phase { display: flex; gap: 10px; align-items: baseline; padding: 2px 0; }
.aris-phase-name { flex: 0 0 60px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.aris-phase-status { flex: 0 0 90px; font-size: 12px; }
.aris-phase-detail { flex: 1; opacity: .65; font-size: 12px; }
.aris-phase-artifact { margin-left: 8px; opacity: .8; }
.aris-run { margin: 0 0 6px; }
.aris-criticisms { margin-top: 10px; }
.aris-criticisms .aris-key { margin-bottom: 3px; }
.aris-status-accepted { color: #2ea043; font-weight: 600; }
.aris-status-done { color: #bf8700; }
.aris-status-running { color: #0969da; }
.aris-status-failed { color: #cf222e; }
.aris-status-pending, .aris-status-skipped { opacity: .5; }
`

    return {
      inject: ['slots', 'connection'],
      apply(ctx) {
        ctx.effect(() => {
          const style = document.createElement('style')
          style.textContent = CSS
          document.head.append(style)
          return () => { style.remove() }
        }, 'ARIS run-status styles')

        ctx.slots.inject('conversation.view', () => ctx.slots.register({
          name: 'conversation.view',
          id: 'aris',
          order: 100,
          label: () => 'ARIS',
        }, (props) => h(ArisRunView, {
          sessionId: props.sessionId,
          connection: ctx.connection,
        })))
      },
    }
  },
})
