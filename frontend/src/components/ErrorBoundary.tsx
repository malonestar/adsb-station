import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
  info: ErrorInfo | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, info: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ error, info })
    // Loud in the console for debugging
    console.error('[ErrorBoundary]', error)
    console.error('[ErrorBoundary] componentStack:', info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-6 min-h-screen bg-bg-0 text-text-hi font-mono text-xs overflow-auto">
          <h1 className="text-efis-red text-base mb-4">UI CRASH</h1>
          <pre className="whitespace-pre-wrap text-efis-amber mb-4">
            {this.state.error.name}: {this.state.error.message}
          </pre>
          <div className="section-header mb-2">Stack</div>
          <pre className="whitespace-pre-wrap text-text-mid mb-4 border border-stroke-hair p-2">
            {this.state.error.stack}
          </pre>
          <div className="section-header mb-2">Component Tree</div>
          <pre className="whitespace-pre-wrap text-text-mid border border-stroke-hair p-2">
            {this.state.info?.componentStack}
          </pre>
        </div>
      )
    }
    return this.props.children
  }
}
