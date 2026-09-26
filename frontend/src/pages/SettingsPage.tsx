import React, { useState, useRef } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Settings,
  Key,
  HardDrive,
  Cpu,
  Check,
  Trash2,
  Plus,
  Sparkles,
  ShieldAlert,
  Terminal,
  Copy,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  Cookie,
  Upload,
  Play,
  FileVideo,
  Edit3,
  Sliders,
} from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { formatDuration, cn } from '../lib/utils';
import { ImportCheckResult, TuningPreset } from '../types';
import { getSavedPresets, savePresets, validatePresetName } from '../lib/presets';

export const SettingsPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Health & Diagnostics
  const { data: health, isLoading: isHealthLoading } = useQuery({
    queryKey: ['health'],
    queryFn: api.getHealth,
  });

  if (health?.app_env === 'demo') {
    return <Navigate to="/" replace />;
  }

  // Copyable command feedback
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  // Preflight Test Import
  const [testUrl, setTestUrl] = useState('');
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<ImportCheckResult | null>(null);

  const handleTestImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testUrl.trim()) return;
    setIsTesting(true);
    setTestResult(null);
    try {
      const res = await api.checkImport(testUrl.trim());
      setTestResult(res);
    } catch (err: any) {
      setTestResult({
        ok: false,
        error_code: 'DOWNLOAD_FAILED',
        message: err.message || 'Check failed',
        hint: 'Verify the URL and backend network connection.',
      });
    } finally {
      setIsTesting(false);
    }
  };

  // Cookies Management
  const [selectedBrowser, setSelectedBrowser] = useState('chrome');
  const [cookieLoading, setCookieLoading] = useState(false);
  const [cookieFeedback, setCookieFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const cookieFileInputRef = useRef<HTMLInputElement>(null);

  const handleSetBrowser = async () => {
    setCookieLoading(true);
    setCookieFeedback(null);
    try {
      await api.setBrowserCookies(selectedBrowser);
      await queryClient.invalidateQueries({ queryKey: ['health'] });
      setCookieFeedback({ type: 'success', message: `Configured cookies from ${selectedBrowser}.` });
    } catch (err: any) {
      setCookieFeedback({ type: 'error', message: err.message || 'Failed to extract browser cookies.' });
    } finally {
      setCookieLoading(false);
    }
  };

  const handleUploadCookies = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCookieLoading(true);
    setCookieFeedback(null);
    try {
      await api.uploadCookiesFile(file);
      await queryClient.invalidateQueries({ queryKey: ['health'] });
      setCookieFeedback({ type: 'success', message: 'cookies.txt uploaded and stored with chmod 0600.' });
      if (cookieFileInputRef.current) cookieFileInputRef.current.value = '';
    } catch (err: any) {
      setCookieFeedback({ type: 'error', message: err.message || 'Failed to upload cookies file.' });
    } finally {
      setCookieLoading(false);
    }
  };

  const handleClearCookies = async () => {
    setCookieLoading(true);
    setCookieFeedback(null);
    try {
      await api.clearCookies();
      await queryClient.invalidateQueries({ queryKey: ['health'] });
      setCookieFeedback({ type: 'success', message: 'Cookies cleared. Using unauthenticated public extraction.' });
    } catch (err: any) {
      setCookieFeedback({ type: 'error', message: err.message || 'Failed to clear cookies.' });
    } finally {
      setCookieLoading(false);
    }
  };

  // API Token
  const [tokenInput, setTokenInput] = useState(() => localStorage.getItem('api_token') || '');
  const [isTokenSaved, setIsTokenSaved] = useState(false);

  const handleSaveToken = () => {
    if (tokenInput.trim()) {
      localStorage.setItem('api_token', tokenInput.trim());
    } else {
      localStorage.removeItem('api_token');
    }
    setIsTokenSaved(true);
    setTimeout(() => setIsTokenSaved(false), 2000);
  };

  // Custom Presets Management
  const [presets, setPresets] = useState<TuningPreset[]>(() => getSavedPresets());
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [presetFormError, setPresetFormError] = useState<string | null>(null);
  const [appliedNotice, setAppliedNotice] = useState<string | null>(null);

  // Form Fields with all basic settings
  const [formName, setFormName] = useState('');
  const [formDuration, setFormDuration] = useState(180);
  const [formSensitivity, setFormSensitivity] = useState(3);
  const [formRise, setFormRise] = useState(4.0);
  const [formSustain, setFormSustain] = useState(3.0);
  const [formSkipStart, setFormSkipStart] = useState(30);
  const [formPreRoll, setFormPreRoll] = useState(12.0);
  const [formPostRoll, setFormPostRoll] = useState(6.0);

  const handleSavePreset = (e: React.FormEvent) => {
    e.preventDefault();
    setPresetFormError(null);

    const validationErr = validatePresetName(formName, presets, editingIndex ?? undefined);
    if (validationErr) {
      setPresetFormError(validationErr);
      return;
    }

    const newPreset: TuningPreset = {
      name: formName.trim(),
      config: {
        target_duration: formDuration,
        sensitivity: formSensitivity,
        min_rise_db: formRise,
        min_sustain_s: formSustain,
        skip_start_s: formSkipStart,
        pre_roll: formPreRoll,
        post_roll: formPostRoll,
      },
    };

    let updated: TuningPreset[];
    if (editingIndex !== null) {
      updated = presets.map((p, idx) => (idx === editingIndex ? newPreset : p));
      setEditingIndex(null);
    } else {
      updated = [...presets, newPreset];
    }

    setPresets(updated);
    savePresets(updated);
    setFormName('');
    setFormDuration(180);
    setFormSensitivity(3);
    setFormRise(4.0);
    setFormSustain(3.0);
    setFormSkipStart(30);
    setFormPreRoll(12.0);
    setFormPostRoll(6.0);
  };

  const handleEditPreset = (index: number) => {
    const p = presets[index];
    setEditingIndex(index);
    setFormName(p.name);
    setFormDuration(p.config.target_duration ?? 180);
    setFormSensitivity(p.config.sensitivity ?? 3);
    setFormRise(p.config.min_rise_db ?? 4.0);
    setFormSustain(p.config.min_sustain_s ?? 3.0);
    setFormSkipStart(p.config.skip_start_s ?? 30);
    setFormPreRoll(p.config.pre_roll ?? 12.0);
    setFormPostRoll(p.config.post_roll ?? 6.0);
    setPresetFormError(null);
  };

  const handleCancelEdit = () => {
    setEditingIndex(null);
    setFormName('');
    setPresetFormError(null);
  };

  const handleDuplicatePreset = (index: number) => {
    const original = presets[index];
    let copyName = `Copy of ${original.name}`;
    let counter = 2;
    while (presets.some((p) => p.name.toLowerCase() === copyName.toLowerCase())) {
      copyName = `Copy of ${original.name} (${counter})`;
      counter++;
    }
    const cloned: TuningPreset = {
      name: copyName,
      config: { ...original.config },
    };
    const updated = [...presets, cloned];
    setPresets(updated);
    savePresets(updated);
  };

  const handleDeletePreset = (index: number) => {
    const updated = presets.filter((_, idx) => idx !== index);
    setPresets(updated);
    savePresets(updated);
    if (editingIndex === index) {
      handleCancelEdit();
    }
  };

  const handleApplyPreset = (preset: TuningPreset) => {
    localStorage.setItem('active_draft_preset', JSON.stringify(preset));
    setAppliedNotice(`Applied "${preset.name}". Redirecting to New Highlight...`);
    setTimeout(() => {
      navigate('/');
    }, 600);
  };

  const jsRuntime = health?.js_runtime;
  const cookiesCfg = health?.cookies;

  return (
    <div className="max-w-4xl mx-auto p-6 sm:p-10 space-y-8">
      <div>
        <h1 className="text-2xl font-extrabold text-text tracking-tight">System Settings & Diagnostics</h1>
        <p className="text-xs text-muted mt-1">
          Monitor video extraction dependencies, authenticate with browser cookies, and manage processing presets.
        </p>
      </div>

      <div className="space-y-6">
        {/* 1. Import Diagnostics & Health Card */}
        <Card>
          <CardHeader>
            <CardTitle>
              <Cpu className="w-5 h-5 text-primary" />
              <span>URL Import Diagnostics</span>
            </CardTitle>
            {health && (
              <Badge variant={health.status === 'healthy' ? 'selected' : 'warning'}>
                {health.status.toUpperCase()}
              </Badge>
            )}
          </CardHeader>

          {health ? (
            <div className="space-y-6">
              {/* Status Tiles Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                {/* yt-dlp Version */}
                <div className="p-3 bg-card rounded-xl border border-border flex flex-col justify-between space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-muted font-semibold">yt-dlp Core</span>
                    <Badge variant="selected">ACTIVE</Badge>
                  </div>
                  <div>
                    <p className="text-sm font-bold text-text truncate">v{health.yt_dlp.version}</p>
                    <p className="text-[10px] text-muted">Latest release installed</p>
                  </div>
                </div>

                {/* yt-dlp-ejs */}
                <div className="p-3 bg-card rounded-xl border border-border flex flex-col justify-between space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-muted font-semibold">yt-dlp-ejs</span>
                    {health.yt_dlp.ejs_installed ? (
                      <Badge variant="selected">INSTALLED</Badge>
                    ) : (
                      <Badge variant="danger">MISSING</Badge>
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-text">
                      {health.yt_dlp.ejs_installed ? 'Solver Plugin Ready' : 'Plugin Required'}
                    </p>
                    <p className="text-[10px] text-muted">JS Challenge Solver</p>
                  </div>
                </div>

                {/* JS Runtime */}
                <div className="p-3 bg-card rounded-xl border border-border flex flex-col justify-between space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-muted font-semibold">JS Runtime</span>
                    {jsRuntime?.available ? (
                      <Badge variant="selected">FOUND</Badge>
                    ) : (
                      <Badge variant="danger">MISSING</Badge>
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-text capitalize">
                      {jsRuntime?.available
                        ? `${jsRuntime.runtime} ${jsRuntime.version || ''}`
                        : 'None on PATH'}
                    </p>
                    <p className="text-[10px] text-muted truncate" title={jsRuntime?.path || ''}>
                      {jsRuntime?.path || 'Install Deno >= 2.3'}
                    </p>
                  </div>
                </div>

                {/* Cookie Source */}
                <div className="p-3 bg-card rounded-xl border border-border flex flex-col justify-between space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-muted font-semibold">Cookies</span>
                    {cookiesCfg?.source && cookiesCfg.source !== 'none' ? (
                      <Badge variant="selected">ENABLED</Badge>
                    ) : (
                      <Badge variant="default">NONE</Badge>
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-bold text-text capitalize">
                      {cookiesCfg?.source === 'browser'
                        ? `Browser (${cookiesCfg.browser})`
                        : cookiesCfg?.source === 'file'
                        ? 'cookies.txt File'
                        : 'Unauthenticated'}
                    </p>
                    <p className="text-[10px] text-muted">
                      {cookiesCfg?.source !== 'none' ? 'Session cookies active' : 'Public streams only'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Fix Commands If Dependency Missing */}
              {(!health.yt_dlp.ejs_installed || !jsRuntime?.available) && (
                <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 space-y-3">
                  <div className="flex items-center gap-2 text-amber-400 font-semibold text-xs">
                    <AlertCircle className="w-4 h-4" />
                    <span>Action Required for YouTube Imports</span>
                  </div>

                  {!health.yt_dlp.ejs_installed && (
                    <div className="flex items-center justify-between bg-black/40 px-3 py-2 rounded-lg border border-border text-xs">
                      <div>
                        <p className="text-text font-semibold">Install yt-dlp-ejs solver</p>
                        <code className="text-muted font-mono text-[11px]">uv add "yt-dlp[default]"</code>
                      </div>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleCopy('uv add "yt-dlp[default]"', 'ejs')}
                        className="gap-1 text-xs"
                      >
                        {copiedKey === 'ejs' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedKey === 'ejs' ? 'Copied' : 'Copy'}</span>
                      </Button>
                    </div>
                  )}

                  {!jsRuntime?.available && (
                    <div className="flex items-center justify-between bg-black/40 px-3 py-2 rounded-lg border border-border text-xs">
                      <div>
                        <p className="text-text font-semibold">Install Deno runtime (&gt;= 2.3)</p>
                        <code className="text-muted font-mono text-[11px]">curl -fsSL https://deno.land/install.sh | sh</code>
                      </div>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => handleCopy('curl -fsSL https://deno.land/install.sh | sh', 'deno')}
                        className="gap-1 text-xs"
                      >
                        {copiedKey === 'deno' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedKey === 'deno' ? 'Copied' : 'Copy'}</span>
                      </Button>
                    </div>
                  )}
                </div>
              )}

              {/* Interactive Test Import Box */}
              <div className="pt-4 border-t border-border space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-text uppercase tracking-wider">Test URL Preflight</span>
                  <span className="text-[11px] text-muted">Runs 15s preflight without downloading video</span>
                </div>

                <form onSubmit={handleTestImport} className="flex gap-2">
                  <input
                    type="url"
                    value={testUrl}
                    onChange={(e) => setTestUrl(e.target.value)}
                    placeholder="https://www.youtube.com/watch?v=... or direct MP4/stream URL"
                    className="flex-1 bg-card border border-border rounded-xl px-4 py-2 text-xs text-text placeholder:text-muted focus:outline-none focus:border-accent"
                  />
                  <Button type="submit" size="sm" isLoading={isTesting} className="gap-1.5 shrink-0">
                    <Play className="w-3.5 h-3.5" />
                    <span>Test Import</span>
                  </Button>
                </form>

                {/* Test Result Card */}
                {testResult && (
                  <div
                    className={cn(
                      'p-3.5 rounded-xl border text-xs',
                      testResult.ok
                        ? 'bg-emerald-500/10 border-emerald-500/30'
                        : 'bg-danger/10 border-danger/30'
                    )}
                  >
                    {testResult.ok ? (
                      <div className="flex items-start gap-3">
                        {testResult.thumbnail ? (
                          <img
                            src={testResult.thumbnail}
                            alt={testResult.title}
                            className="w-20 h-12 object-cover rounded border border-border bg-black/40 shrink-0"
                          />
                        ) : (
                          <div className="w-20 h-12 rounded bg-card border border-border flex items-center justify-center shrink-0">
                            <FileVideo className="w-6 h-6 text-emerald-400" />
                          </div>
                        )}
                        <div className="space-y-1 min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <Badge variant="selected">PREFLIGHT PASSED</Badge>
                            {testResult.duration_s > 0 && (
                              <span className="font-mono text-muted">{formatDuration(testResult.duration_s)}</span>
                            )}
                            {testResult.est_size_mb && (
                              <span className="font-mono text-muted">• ~{Math.round(testResult.est_size_mb)} MB</span>
                            )}
                          </div>
                          <p className="font-semibold text-text truncate">{testResult.title}</p>
                          <p className="text-[11px] text-emerald-400 font-mono">
                            Stream extracted successfully with active configuration.
                          </p>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-2">
                          <Badge variant="danger">{testResult.error_code}</Badge>
                          <span className="font-bold text-text">{testResult.message}</span>
                        </div>
                        <p className="text-muted text-[11px] leading-relaxed">{testResult.hint}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <p className="text-xs text-muted">Checking diagnostics...</p>
          )}
        </Card>

        {/* 2. Optional Cookies Management Card */}
        <Card>
          <CardHeader>
            <CardTitle>
              <Cookie className="w-5 h-5 text-amber-400" />
              <span>Authentication & Cookies</span>
            </CardTitle>
            {cookiesCfg?.source && cookiesCfg.source !== 'none' ? (
              <Badge variant="selected">ACTIVE</Badge>
            ) : (
              <Badge variant="default">DISABLED</Badge>
            )}
          </CardHeader>

          <div className="space-y-5">
            {/* Account Risk Warning Alert */}
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-start gap-3">
              <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div className="space-y-1 text-xs">
                <h4 className="font-bold text-text">Account Security Notice</h4>
                <p className="text-muted leading-relaxed">
                  Importing cookies from your browser or a <code className="font-mono text-text">cookies.txt</code> file passes your active authenticated Google session to yt-dlp to bypass YouTube bot challenges. This action uses your real signed-in account and carries a potential risk of temporary rate limits or account restrictions by YouTube.
                </p>
                <p className="text-amber-400 font-semibold pt-1">
                  Recommendation: Use a dedicated or throwaway Google account rather than your primary personal account.
                </p>
              </div>
            </div>

            {/* Active Cookies Banner */}
            {cookiesCfg && cookiesCfg.source !== 'none' && (
              <div className="p-3 bg-card rounded-xl border border-border flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span className="font-semibold text-text">
                    Active Source: {cookiesCfg.source === 'browser' ? `Browser (${cookiesCfg.browser})` : 'Uploaded cookies.txt'}
                  </span>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleClearCookies}
                  isLoading={cookieLoading}
                  className="text-xs hover:text-danger hover:border-danger/40"
                >
                  Clear Cookies
                </Button>
              </div>
            )}

            {/* Configure Controls */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Option 1: Browser Cookies */}
              <div className="p-4 bg-card rounded-xl border border-border space-y-3 flex flex-col justify-between">
                <div className="space-y-1">
                  <h4 className="text-xs font-bold text-text">Option A: Browser Cookies</h4>
                  <p className="text-[11px] text-muted">Extract session cookies automatically from an installed browser.</p>
                </div>

                <div className="space-y-2 pt-2">
                  <select
                    value={selectedBrowser}
                    onChange={(e) => setSelectedBrowser(e.target.value)}
                    className="w-full bg-surface border border-border rounded-lg px-3 py-2 text-xs text-text capitalize focus:outline-none focus:border-accent"
                  >
                    <option value="chrome">Google Chrome</option>
                    <option value="safari">Apple Safari</option>
                    <option value="firefox">Mozilla Firefox</option>
                    <option value="brave">Brave Browser</option>
                    <option value="edge">Microsoft Edge</option>
                  </select>

                  <Button
                    onClick={handleSetBrowser}
                    isLoading={cookieLoading}
                    size="sm"
                    className="w-full text-xs"
                  >
                    Use {selectedBrowser} Cookies
                  </Button>
                </div>
              </div>

              {/* Option 2: Upload cookies.txt */}
              <div className="p-4 bg-card rounded-xl border border-border space-y-3 flex flex-col justify-between">
                <div className="space-y-1">
                  <h4 className="text-xs font-bold text-text">Option B: Upload cookies.txt</h4>
                  <p className="text-[11px] text-muted">
                    Stored in <code className="font-mono text-text">data/cookies.txt</code> with chmod 0600. File contents are never logged.
                  </p>
                </div>

                <div className="pt-2">
                  <input
                    ref={cookieFileInputRef}
                    type="file"
                    accept=".txt"
                    className="hidden"
                    onChange={handleUploadCookies}
                  />
                  <Button
                    onClick={() => cookieFileInputRef.current?.click()}
                    isLoading={cookieLoading}
                    variant="secondary"
                    size="sm"
                    className="w-full text-xs gap-1.5"
                  >
                    <Upload className="w-3.5 h-3.5" />
                    <span>Upload cookies.txt</span>
                  </Button>
                </div>
              </div>
            </div>

            {/* Cookie Feedback */}
            {cookieFeedback && (
              <div
                className={cn(
                  'p-3 rounded-lg text-xs flex items-center gap-2 border',
                  cookieFeedback.type === 'success'
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    : 'bg-danger/10 border-danger/30 text-danger'
                )}
              >
                {cookieFeedback.type === 'success' ? (
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                ) : (
                  <AlertCircle className="w-4 h-4 shrink-0" />
                )}
                <span>{cookieFeedback.message}</span>
              </div>
            )}
          </div>
        </Card>

        {/* 3. API Authentication Card - Only visible when auth_required = true */}
        {health?.auth_required && (
          <Card>
            <CardHeader>
              <CardTitle>
                <Key className="w-5 h-5 text-accent" />
                <span>API Bearer Token</span>
              </CardTitle>
            </CardHeader>

            <div className="space-y-3">
              <p className="text-xs text-muted leading-relaxed">
                Your backend server was started with an <code className="font-mono text-text bg-card px-1 py-0.5 rounded">API_TOKEN</code> requirement. Provide it here so client requests are authenticated.
              </p>

              <div className="flex items-center gap-3">
                <input
                  type="password"
                  value={tokenInput}
                  onChange={(e) => setTokenInput(e.target.value)}
                  placeholder="Enter secret API token..."
                  className="flex-1 bg-card border border-border rounded-xl px-4 py-2 text-sm text-text font-mono focus:outline-none focus:border-accent"
                />
                <Button onClick={handleSaveToken} size="md" className="gap-2">
                  {isTokenSaved ? <Check className="w-4 h-4 text-emerald-300" /> : null}
                  <span>{isTokenSaved ? 'Saved!' : 'Save Token'}</span>
                </Button>
              </div>
            </div>
          </Card>
        )}

        {/* 4. Custom Tuning Presets Card */}
        <Card>
          <CardHeader>
            <CardTitle>
              <Sparkles className="w-5 h-5 text-amber-400" />
              <span>Custom Tuning Presets</span>
            </CardTitle>
          </CardHeader>

          <div className="space-y-5">
            <p className="text-xs text-muted leading-relaxed">
              Preset profiles bundle detection thresholds, lead-in buffers, and length caps. Select a preset to apply it to new jobs, or configure custom hyperparameter sets.
            </p>

            {appliedNotice && (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs font-semibold text-emerald-400 flex items-center gap-2 animate-in fade-in">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{appliedNotice}</span>
              </div>
            )}

            {/* Presets List as Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {presets.map((p, idx) => (
                <div
                  key={p.name}
                  className={cn(
                    'p-4 rounded-xl border transition-all space-y-3 bg-card/60 flex flex-col justify-between',
                    editingIndex === idx ? 'border-primary ring-1 ring-primary' : 'border-border hover:border-border/80'
                  )}
                >
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-sm text-text">{p.name}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-accent/10 text-accent border border-accent/20">
                        Level {p.config.sensitivity ?? 3}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 text-[11px] text-muted font-mono">
                      <div>
                        <span className="text-[10px] text-muted/80 block uppercase">Length Cap</span>
                        <span className="text-text font-semibold">
                          {p.config.target_duration === 0 ? 'Full / None' : formatDuration(p.config.target_duration)}
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-muted/80 block uppercase">Min Rise</span>
                        <span className="text-text font-semibold">{p.config.min_rise_db} dB</span>
                      </div>
                      <div>
                        <span className="text-[10px] text-muted/80 block uppercase">Min Sustain</span>
                        <span className="text-text font-semibold">{p.config.min_sustain_s}s</span>
                      </div>
                      <div>
                        <span className="text-[10px] text-muted/80 block uppercase">Skip Start</span>
                        <span className="text-text font-semibold">{p.config.skip_start_s}s</span>
                      </div>
                      <div>
                        <span className="text-[10px] text-muted/80 block uppercase">Pre-Roll</span>
                        <span className="text-text font-semibold">{p.config.pre_roll}s</span>
                      </div>
                      <div>
                        <span className="text-[10px] text-muted/80 block uppercase">Post-Roll</span>
                        <span className="text-text font-semibold">{p.config.post_roll}s</span>
                      </div>
                    </div>
                  </div>

                  <div className="pt-2 border-t border-border/50 flex items-center justify-between gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="primary"
                      onClick={() => handleApplyPreset(p)}
                      className="gap-1.5 text-xs py-1"
                    >
                      <Play className="w-3 h-3 fill-current" />
                      <span>Apply</span>
                    </Button>

                    <div className="flex items-center gap-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => handleEditPreset(idx)}
                        className="p-1.5 h-8 w-8 text-muted hover:text-text"
                        title="Edit preset"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDuplicatePreset(idx)}
                        className="p-1.5 h-8 w-8 text-muted hover:text-text"
                        title="Duplicate preset"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDeletePreset(idx)}
                        className="p-1.5 h-8 w-8 text-muted hover:text-danger"
                        title="Delete preset"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Add / Edit Preset Form */}
            <div className="pt-4 border-t border-border/80 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-text uppercase tracking-wider">
                  {editingIndex !== null ? `Edit Preset: "${presets[editingIndex]?.name}"` : 'Add New Custom Preset'}
                </span>
                {editingIndex !== null && (
                  <Button type="button" size="sm" variant="ghost" onClick={handleCancelEdit} className="text-xs py-1">
                    Cancel Edit
                  </Button>
                )}
              </div>

              {presetFormError && (
                <div className="p-3 bg-danger/10 border border-danger/30 rounded-xl text-xs text-danger flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{presetFormError}</span>
                </div>
              )}

              <form onSubmit={handleSavePreset} className="space-y-4 p-4 bg-surface/50 border border-border rounded-xl">
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="sm:col-span-2 space-y-1">
                    <label className="text-xs font-semibold text-text">Preset Name</label>
                    <input
                      type="text"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      placeholder="e.g. World Cup Final Derby"
                      className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-text focus:outline-none focus:border-accent"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-text">Length Cap (seconds)</label>
                    <input
                      type="number"
                      min="0"
                      max="3600"
                      step="30"
                      value={formDuration}
                      onChange={(e) => setFormDuration(parseInt(e.target.value) || 0)}
                      placeholder="0 for full"
                      className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-text font-mono focus:outline-none focus:border-accent"
                      title="Target reel duration cap in seconds (0 = full)"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-text">Sensitivity Level (1-5)</label>
                    <input
                      type="number"
                      min="1"
                      max="5"
                      step="1"
                      value={formSensitivity}
                      onChange={(e) => setFormSensitivity(parseInt(e.target.value) || 3)}
                      className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-text font-mono focus:outline-none focus:border-accent"
                      title="Sensitivity level from 1 (conservative) to 5 (sensitive)"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-text">Min Rise (dB)</label>
                    <input
                      type="number"
                      min="1"
                      max="15"
                      step="0.5"
                      value={formRise}
                      onChange={(e) => setFormRise(parseFloat(e.target.value) || 4.0)}
                      className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-text font-mono focus:outline-none focus:border-accent"
                      title="Minimum volume rise above baseline (dB)"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-text">Min Sustain (seconds)</label>
                    <input
                      type="number"
                      min="1"
                      max="8"
                      step="0.5"
                      value={formSustain}
                      onChange={(e) => setFormSustain(parseFloat(e.target.value) || 3.0)}
                      className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-text font-mono focus:outline-none focus:border-accent"
                      title="Minimum excitement duration in seconds"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-text">Skip Start (seconds)</label>
                    <input
                      type="number"
                      min="0"
                      max="600"
                      step="5"
                      value={formSkipStart}
                      onChange={(e) => setFormSkipStart(parseFloat(e.target.value) || 0)}
                      className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-text font-mono focus:outline-none focus:border-accent"
                      title="Seconds to skip at beginning of video"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-text">Pre-Roll (seconds)</label>
                    <input
                      type="number"
                      min="0"
                      max="60"
                      step="1"
                      value={formPreRoll}
                      onChange={(e) => setFormPreRoll(parseFloat(e.target.value) || 12.0)}
                      className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-text font-mono focus:outline-none focus:border-accent"
                      title="Lead-in buffer before peak in seconds"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-text">Post-Roll (seconds)</label>
                    <input
                      type="number"
                      min="0"
                      max="60"
                      step="1"
                      value={formPostRoll}
                      onChange={(e) => setFormPostRoll(parseFloat(e.target.value) || 6.0)}
                      className="w-full bg-card border border-border rounded-lg px-3 py-1.5 text-xs text-text font-mono focus:outline-none focus:border-accent"
                      title="Cool-down buffer after peak in seconds"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2">
                  <Button type="submit" size="sm" variant="primary" className="gap-1.5">
                    <Check className="w-3.5 h-3.5" />
                    <span>{editingIndex !== null ? 'Update Preset' : 'Save Preset'}</span>
                  </Button>
                </div>
              </form>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

