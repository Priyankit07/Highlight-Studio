import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Navbar } from './components/layout/Navbar';
import { ToastProvider } from './components/ui/Toast';
import { NewJobPage } from './pages/NewJobPage';
import { JobStudioPage } from './pages/JobStudioPage';
import { LibraryPage } from './pages/LibraryPage';
import { SettingsPage } from './pages/SettingsPage';
import { ErrorBoundary } from './components/ui/ErrorBoundary';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 5000,
    },
  },
});

const JobStudioRoute: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  return (
    <ErrorBoundary jobId={id} isRouteBoundary>
      <JobStudioPage />
    </ErrorBoundary>
  );
};

export const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <div className="min-h-screen flex flex-col bg-bg text-text antialiased selection:bg-primary/20 selection:text-primary relative overflow-x-hidden">
              {/* Subtle soccer pitch markings motif in background */}
              <div
                className="fixed inset-0 pointer-events-none opacity-[0.025] dark:opacity-[0.04] z-0"
                style={{
                  backgroundImage: `radial-gradient(circle at center, rgba(16, 185, 129, 0.4) 1px, transparent 1px), linear-gradient(to bottom, transparent 49.5%, rgba(16, 185, 129, 0.2) 50%, transparent 50.5%)`,
                  backgroundSize: '32px 32px, 100% 100%',
                }}
              />

              <Navbar />

              <main className="flex-1 flex flex-col relative z-10">
                <ErrorBoundary isRouteBoundary>
                  <Routes>
                    <Route path="/" element={<NewJobPage />} />
                    <Route path="/jobs/:id" element={<JobStudioRoute />} />
                    <Route path="/library" element={<LibraryPage />} />
                    <Route path="/settings" element={<SettingsPage />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </ErrorBoundary>
              </main>

            <footer className="border-t border-border/60 py-4 px-6 text-center text-xs text-muted relative z-10 bg-surface/30">
              <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-2 h-2 rounded-full bg-primary/70"></span>
                  Football Highlight Studio &bull; Audio excitement analysis
                </span>
                <span className="font-mono text-[11px] text-muted/70">
                  Local-first processing &bull; Zero external cloud dependencies
                </span>
              </div>
            </footer>
          </div>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  </ErrorBoundary>
);
};

export default App;
