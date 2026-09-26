import React, { useState, useEffect, useRef } from 'react';
import { X, Sliders, RotateCcw, Loader2, Sparkles, ChevronDown, ChevronUp, Info } from 'lucide-react';
import { Button } from '../ui/Button';
import { Slider } from '../ui/Slider';
import { SENSITIVITY_LEVELS, sensitivityToParams, paramsToSensitivity, cn } from '../../lib/utils';
import { ConfigFieldSchema } from '../../types';

export interface TuningDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  config: Record<string, any>;
  schemaFields: ConfigFieldSchema[];
  onRetune: (overrides: Record<string, any>) => Promise<void>;
  isRetuning: boolean;
}

export const TuningDrawer: React.FC<TuningDrawerProps> = ({
  isOpen,
  onClose,
  config,
  schemaFields,
  onRetune,
  isRetuning,
}) => {
  const [localConfig, setLocalConfig] = useState<Record<string, any>>(config);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [sensitivityLevel, setSensitivityLevel] = useState<number>(3);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLocalConfig(config);
    if (config.min_rise_db !== undefined && config.min_sustain_s !== undefined) {
      setSensitivityLevel(paramsToSensitivity(config.min_rise_db, config.min_sustain_s));
    }
  }, [config]);

  // Debounced auto-retune trigger (600ms)
  const triggerRetune = (newConfig: Record<string, any>) => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      onRetune(newConfig);
    }, 600);
  };

  const handleSensitivityChange = (level: number) => {
    setSensitivityLevel(level);
    const params = sensitivityToParams(level);
    const updated = {
      ...localConfig,
      min_rise_db: params.min_rise_db,
      min_sustain_s: params.min_sustain_s,
    };
    setLocalConfig(updated);
    triggerRetune(updated);
  };

  const handleFieldChange = (key: string, value: any) => {
    const updated = { ...localConfig, [key]: value };
    setLocalConfig(updated);
    if (key === 'min_rise_db' || key === 'min_sustain_s') {
      setSensitivityLevel(paramsToSensitivity(updated.min_rise_db, updated.min_sustain_s));
    }
    triggerRetune(updated);
  };

  const handleReset = () => {
    const defaults: Record<string, any> = {};
    schemaFields.forEach((f) => {
      defaults[f.name] = f.default;
    });
    setLocalConfig(defaults);
    setSensitivityLevel(3);
    triggerRetune(defaults);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="w-full max-w-md bg-surface border-l border-border h-full flex flex-col shadow-2xl animate-in slide-in-from-right duration-200">
        {/* Drawer Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/80 bg-card/60">
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-primary" />
            <h3 className="text-base font-bold text-text">Detection Tuning</h3>
            {isRetuning && (
              <span className="flex items-center gap-1.5 text-xs text-primary font-mono ml-2">
                <Loader2 className="w-3 h-3 animate-spin" />
                <span>Re-analysing...</span>
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-muted hover:text-text hover:bg-card transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Form Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Sensitivity Slider */}
          <div className="bg-card/50 p-4 rounded-xl border border-border space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-text uppercase tracking-wider">Detection Sensitivity</label>
              <span className="text-xs font-mono font-bold text-primary">
                {SENSITIVITY_LEVELS.find((s) => s.level === sensitivityLevel)?.label}
              </span>
            </div>
            <input
              type="range"
              min={1}
              max={5}
              step={1}
              value={sensitivityLevel}
              onChange={(e) => handleSensitivityChange(parseInt(e.target.value))}
              className="w-full h-1.5 bg-border rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <p className="text-xs text-muted">
              {SENSITIVITY_LEVELS.find((s) => s.level === sensitivityLevel)?.desc}
            </p>
          </div>

          {/* Quick Reel Duration Presets */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-text uppercase tracking-wider">Target Reel Cap</label>
            <div className="grid grid-cols-3 gap-1.5">
              {[
                { label: '2 min', val: 120 },
                { label: '5 min', val: 300 },
                { label: '8 min', val: 480 },
                { label: '12 min', val: 720 },
                { label: 'All', val: 0 },
              ].map((p) => {
                const isActive = localConfig.target_duration === p.val;
                return (
                  <button
                    key={p.val}
                    type="button"
                    onClick={() => handleFieldChange('target_duration', p.val)}
                    className={cn(
                      'px-2 py-1.5 rounded-lg text-xs font-mono font-medium border transition-all',
                      isActive
                        ? 'bg-primary/20 text-primary border-primary/40 font-bold'
                        : 'bg-card text-muted hover:text-text border-border'
                    )}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
            <p className="text-[11px] text-muted">
              * A cap, not a quota. Reel includes moments actually detected up to this limit.
            </p>
          </div>

          {/* Lead-in and Reaction Sliders */}
          <div className="space-y-4 pt-2 border-t border-border/40">
            <Slider
              label="Pre-Roll Lead-In"
              description="Seconds of footage included before excitement peak to capture build-up play"
              min={2}
              max={30}
              step={1}
              unit="s"
              value={localConfig.pre_roll ?? 12}
              onChange={(e) => handleFieldChange('pre_roll', parseFloat(e.target.value))}
            />

            <Slider
              label="Post-Roll Reaction"
              description="Seconds of footage included after excitement subsides for celebrations and reactions"
              min={2}
              max={25}
              step={1}
              unit="s"
              value={localConfig.post_roll ?? 6}
              onChange={(e) => handleFieldChange('post_roll', parseFloat(e.target.value))}
            />
          </div>

          {/* Contextual Hints from README Guide */}
          <div className="bg-sky-950/20 border border-sky-800/40 rounded-xl p-4 text-xs space-y-2 text-sky-200">
            <div className="flex items-center gap-2 font-semibold text-sky-400">
              <Info className="w-4 h-4" />
              <span>Tuning Tips</span>
            </div>
            <ul className="space-y-1.5 list-disc list-inside text-muted text-[11px] leading-relaxed">
              <li><strong className="text-text">Too many moments?</strong> Raise sensitivity to 1 or 2 (higher Min rise threshold).</li>
              <li><strong className="text-text">Missing legitimate crowd peaks?</strong> Lower sensitivity to 4 or 5.</li>
              <li><strong className="text-text">Intro music detected?</strong> Increase Skip Start in advanced options.</li>
            </ul>
          </div>

          {/* Advanced Accordion */}
          <div className="pt-2 border-t border-border/40">
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="w-full flex items-center justify-between py-2 text-xs font-bold text-muted hover:text-text uppercase tracking-wider"
            >
              <span>Advanced Detection Hyperparameters</span>
              {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {showAdvanced && (
              <div className="space-y-4 pt-3 animate-in fade-in duration-150">
                <Slider
                  label="Min Rise Threshold"
                  description="Acoustic excitement rise above 90s rolling baseline"
                  min={1.0}
                  max={15.0}
                  step={0.5}
                  unit="dB"
                  value={localConfig.min_rise_db ?? 4.0}
                  onChange={(e) => handleFieldChange('min_rise_db', parseFloat(e.target.value))}
                />

                <Slider
                  label="Min Sustain Duration"
                  description="Rejects short transients (whistles, kicks, microphone thumps)"
                  min={1.0}
                  max={8.0}
                  step={0.5}
                  unit="s"
                  value={localConfig.min_sustain_s ?? 3.0}
                  onChange={(e) => handleFieldChange('min_sustain_s', parseFloat(e.target.value))}
                />

                <Slider
                  label="Skip Start"
                  description="Initial broadcast duration ignored (intro jingles & studio graphics)"
                  min={0}
                  max={300}
                  step={5}
                  unit="s"
                  value={localConfig.skip_start_s ?? 30}
                  onChange={(e) => handleFieldChange('skip_start_s', parseFloat(e.target.value))}
                />

                <Slider
                  label="Merge Gap"
                  description="Consecutive windows within this gap become one highlight"
                  min={0}
                  max={15}
                  step={0.5}
                  unit="s"
                  value={localConfig.merge_gap ?? 2.0}
                  onChange={(e) => handleFieldChange('merge_gap', parseFloat(e.target.value))}
                />

                <Slider
                  label="Fade Duration"
                  description="Duration of video and audio fade transitions"
                  min={0.0}
                  max={1.0}
                  step={0.05}
                  unit="s"
                  value={localConfig.fade_duration_s ?? 0.25}
                  onChange={(e) => handleFieldChange('fade_duration_s', parseFloat(e.target.value))}
                />

                <div className="space-y-1.5 pt-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-text uppercase tracking-wider">Score Ranking Mode</label>
                    <span className="text-xs font-mono font-bold text-primary capitalize">{localConfig.score_mode ?? 'area'}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-1.5">
                    {[
                      { id: 'area', label: 'Area (Default)', desc: 'Rank by excitement envelope integral' },
                      { id: 'peak', label: 'Peak (Rise dB)', desc: 'Rank by peak excitement rise' },
                      { id: 'blend', label: 'Blend', desc: 'Normalized blend of area and peak rise' },
                    ].map((mode) => (
                      <button
                        key={mode.id}
                        type="button"
                        onClick={() => handleFieldChange('score_mode', mode.id)}
                        className={cn(
                          'px-2 py-1.5 rounded-lg text-xs font-medium border transition-all text-center',
                          (localConfig.score_mode ?? 'area') === mode.id
                            ? 'bg-primary/20 text-primary border-primary/40 font-bold'
                            : 'bg-card text-muted hover:text-text border-border'
                        )}
                        title={mode.desc}
                      >
                        {mode.label}
                      </button>
                    ))}
                  </div>
                  <p className="text-[11px] text-muted">
                    Determines how candidate moments are ordered and selected when duration budget caps are enforced.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Drawer Footer */}
        <div className="p-4 bg-card/60 border-t border-border/80 flex items-center justify-between">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleReset}
            className="text-muted hover:text-text gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset to Defaults</span>
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={onClose}
          >
            Done Tuning
          </Button>
        </div>
      </div>
    </div>
  );
};
