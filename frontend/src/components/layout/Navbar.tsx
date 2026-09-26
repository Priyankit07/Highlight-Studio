import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Activity, Film, Moon, Sun, PlusCircle, Settings, HardDrive } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api';
import { cn } from '../../lib/utils';

export const Navbar: React.FC = () => {
  const location = useLocation();
  const [isDark, setIsDark] = useState(() => {
    return document.documentElement.classList.contains('dark') || !localStorage.getItem('theme') || localStorage.getItem('theme') === 'dark';
  });

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('light');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
      localStorage.setItem('theme', 'light');
    }
  }, [isDark]);

  const { data: health, isError: isHealthError } = useQuery({
    queryKey: ['health'],
    queryFn: api.getHealth,
    refetchInterval: (query) => (query.state.status === 'error' ? 4000 : 30000),
    retry: 2,
  });

  const isDemo = health?.app_env === 'demo';

  const navItems = [
    { label: 'New Highlight', href: '/', icon: PlusCircle },
    { label: 'Library', href: '/library', icon: Film },
    ...(!isDemo ? [{ label: 'Settings', href: '/settings', icon: Settings }] : []),
  ];

  return (
    <header className="sticky top-0 z-40 bg-surface/90 backdrop-blur-md border-b border-border/80 transition-colors">
      {/* Global Server Unreachable Banner */}
      {isHealthError && (
        <div className="bg-amber-500 text-slate-950 px-4 py-1.5 text-xs font-semibold text-center flex items-center justify-center gap-2 shadow-sm animate-pulse">
          <Activity className="w-4 h-4 shrink-0" />
          <span>Server unreachable, retrying...</span>
        </div>
      )}

      <div className="max-w-7xl mx-auto px-6 py-3.5 flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-9 h-9 rounded-lg bg-primary/10 border border-primary/30 flex items-center justify-center text-xl group-hover:scale-105 transition-transform shadow-sm shadow-primary/10">
            ⚽
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-base tracking-tight text-text">Highlight Studio</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-primary/20 text-primary border border-primary/30">
                PRO
              </span>
            </div>
            <p className="text-[11px] text-muted -mt-0.5">Adaptive Audio Excitement Detection</p>
          </div>
        </Link>

        {/* Navigation Links */}
        <nav className="flex items-center gap-1 bg-card/60 p-1 rounded-xl border border-border">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.href || (item.href !== '/' && location.pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                to={item.href}
                className={cn(
                  'flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all',
                  isActive
                    ? 'bg-surface text-text font-semibold shadow-sm border border-border/60'
                    : 'text-muted hover:text-text hover:bg-surface/50'
                )}
              >
                <Icon className={cn('w-4 h-4', isActive ? 'text-primary' : 'text-muted')} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Right side status and theme toggle */}
        <div className="flex items-center gap-3">
          {health && (
            <div
              className="hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-lg bg-card/60 border border-border text-xs text-muted"
              title={`FFmpeg: ${health.ffmpeg.available ? 'Ready' : 'Missing'} | Disk Free: ${health.disk.free_gb} GB`}
            >
              <span className="relative flex h-2 w-2">
                <span className={cn('animate-ping absolute inline-flex h-full w-full rounded-full opacity-75', health.status === 'healthy' ? 'bg-primary' : 'bg-amber-400')}></span>
                <span className={cn('relative inline-flex rounded-full h-2 w-2', health.status === 'healthy' ? 'bg-primary' : 'bg-amber-400')}></span>
              </span>
              <span className="font-mono text-[11px]">{health.disk.free_gb} GB Free</span>
            </div>
          )}

          <button
            onClick={() => setIsDark(!isDark)}
            className="p-2 rounded-lg bg-card border border-border text-muted hover:text-text hover:border-accent/40 transition-colors"
            title={isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
            aria-label="Toggle theme"
          >
            {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-sky-500" />}
          </button>
        </div>
      </div>
    </header>
  );
};
