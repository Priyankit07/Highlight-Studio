import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RotateCcw, Film } from 'lucide-react';
import { Button } from './Button';

interface Props {
  children: ReactNode;
  jobId?: string;
  isRouteBoundary?: boolean;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary caught error]', {
      jobId: this.props.jobId || 'N/A',
      error,
      componentStack: errorInfo.componentStack,
    });
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-[50vh] flex flex-col items-center justify-center p-6 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-danger/15 border border-danger/30 flex items-center justify-center text-danger mx-auto">
            <AlertTriangle className="w-6 h-6" />
          </div>
          <div className="space-y-2 max-w-md w-full">
            <h2 className="text-lg font-bold text-text">Something went wrong on this page</h2>
            <details className="text-left bg-card/80 border border-border rounded-lg p-3 cursor-pointer">
              <summary className="text-xs font-semibold text-muted hover:text-text transition-colors">
                Details
              </summary>
              <pre className="mt-2 text-[11px] font-mono text-danger/90 whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
                {this.state.error?.stack || this.state.error?.message || 'An unexpected rendering error occurred.'}
              </pre>
            </details>
          </div>
          <div className="flex items-center gap-2 pt-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => window.location.reload()}
              className="gap-1.5 text-xs"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reload</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                window.location.href = '/library';
              }}
              className="gap-1.5 text-xs"
            >
              <Film className="w-3.5 h-3.5" />
              <span>Back to Library</span>
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

