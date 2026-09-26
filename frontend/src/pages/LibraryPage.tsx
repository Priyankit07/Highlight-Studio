import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Film, Trash2, Edit3, Download, Play, Plus, Clock, Sparkles } from 'lucide-react';
import { api } from '../lib/api';
import { JobSummary } from '../types';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Modal } from '../components/ui/Modal';
import { formatDuration, formatTimeHMS, cn } from '../lib/utils';

export const LibraryPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [jobToDelete, setJobToDelete] = useState<JobSummary | null>(null);
  const [editingTitleId, setEditingTitleId] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => api.listJobs(100, 0),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteJob(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      setJobToDelete(null);
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => api.updateJobTitle(id, title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      setEditingTitleId(null);
    },
  });

  const jobs = data?.jobs || [];

  return (
    <div className="max-w-7xl mx-auto p-6 sm:p-10 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-text tracking-tight">Project Library</h1>
          <p className="text-xs text-muted mt-1">Manage previously processed football matches and download generated reels.</p>
        </div>

        <Button onClick={() => navigate('/')} size="sm" className="gap-2">
          <Plus className="w-4 h-4" />
          <span>New Highlight</span>
        </Button>
      </div>

      {/* Grid of Job Cards */}
      {jobs.length === 0 && !isLoading ? (
        <div className="bg-surface border border-border rounded-2xl p-12 text-center flex flex-col items-center justify-center gap-4">
          <div className="w-16 h-16 rounded-2xl bg-card border border-border flex items-center justify-center text-muted">
            <Film className="w-8 h-8" />
          </div>
          <div>
            <h3 className="text-base font-bold text-text">No highlight reels yet</h3>
            <p className="text-xs text-muted max-w-sm mt-1">
              Upload your first match recording to extract crowd excitement highlights.
            </p>
          </div>
          <Button onClick={() => navigate('/')} variant="primary" size="sm" className="mt-2">
            Create First Highlight
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {jobs.map((job) => (
            <div
              key={job.id}
              className="group bg-surface border border-border rounded-xl overflow-hidden shadow-sm hover:border-accent/40 hover:shadow-md transition-all flex flex-col"
            >
              {/* Card Image / Preview */}
              <div
                onClick={() => navigate(`/jobs/${job.id}`)}
                className="relative aspect-video bg-black cursor-pointer overflow-hidden flex items-center justify-center"
              >
                {job.thumbnail_url ? (
                  <img
                    src={job.thumbnail_url}
                    alt={job.title}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  />
                ) : (
                  <div className="text-muted flex flex-col items-center gap-2">
                    <Film className="w-8 h-8 opacity-40" />
                    <span className="text-[11px] font-mono">No thumbnail preview</span>
                  </div>
                )}

                {/* Status Badge */}
                <div className="absolute top-3 left-3">
                  <Badge
                    variant={
                      job.status === 'completed'
                        ? 'selected'
                        : job.status === 'failed' || job.status === 'cancelled' || job.status === 'interrupted'
                        ? 'danger'
                        : 'accent'
                    }
                  >
                    {job.status.replace('_', ' ')}
                  </Badge>
                </div>

                {/* Reel Length Chip */}
                {job.reel_length > 0 && (
                  <div className="absolute bottom-3 right-3 bg-black/80 px-2 py-0.5 rounded font-mono text-xs text-text border border-border">
                    {formatTimeHMS(job.reel_length)}
                  </div>
                )}
              </div>

              {/* Details Body */}
              <div className="p-4 flex-1 flex flex-col justify-between space-y-4">
                <div className="space-y-1.5">
                  {editingTitleId === job.id ? (
                    <div className="flex items-center gap-1.5">
                      <input
                        type="text"
                        value={newTitle}
                        onChange={(e) => setNewTitle(e.target.value)}
                        className="bg-card border border-border rounded px-2 py-1 text-sm text-text w-full focus:outline-none focus:border-accent"
                        autoFocus
                      />
                      <Button
                        size="sm"
                        onClick={() => renameMutation.mutate({ id: job.id, title: newTitle })}
                      >
                        Save
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-2">
                      <h3
                        onClick={() => navigate(`/jobs/${job.id}`)}
                        className="font-bold text-text text-sm hover:text-accent cursor-pointer truncate"
                      >
                        {job.title}
                      </h3>
                      <button
                        onClick={() => {
                          setEditingTitleId(job.id);
                          setNewTitle(job.title);
                        }}
                        className="text-muted hover:text-text p-1"
                        title="Rename title"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}

                  <div className="flex items-center gap-3 text-xs text-muted font-mono">
                    <span>{job.moment_count} moments</span>
                    <span>•</span>
                    <span>Source: {formatTimeHMS(job.duration_s)}</span>
                  </div>

                  <p className="text-[11px] text-muted">
                    Created: {new Date(job.created_at).toLocaleDateString()} at {new Date(job.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>

                {/* Actions Row */}
                <div className="pt-3 border-t border-border/60 flex items-center justify-between">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(`/jobs/${job.id}`)}
                    className="gap-1.5 text-xs"
                  >
                    <Play className="w-3.5 h-3.5" />
                    <span>Open Studio</span>
                  </Button>

                  <div className="flex items-center gap-1">
                    {job.status === 'completed' && (
                      <a
                        href={`/api/jobs/${job.id}/media/renders/default/highlights.mp4?download=1`}
                        className="p-2 rounded-lg text-muted hover:text-text hover:bg-card transition-colors"
                        title="Download MP4 reel"
                        download
                      >
                        <Download className="w-4 h-4" />
                      </a>
                    )}

                    <button
                      onClick={() => setJobToDelete(job)}
                      className="p-2 rounded-lg text-muted hover:text-danger hover:bg-card transition-colors"
                      title="Delete project"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!jobToDelete}
        onClose={() => setJobToDelete(null)}
        title="Delete Highlight Project?"
        description={`Permanently remove "${jobToDelete?.title}" and its generated assets.`}
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={() => setJobToDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              isLoading={deleteMutation.isPending}
              onClick={() => jobToDelete && deleteMutation.mutate(jobToDelete.id)}
            >
              Delete Project
            </Button>
          </>
        }
      >
        <p className="text-xs text-muted">
          All audio waveforms, analysis manifests, and rendered video clips will be deleted from disk.
        </p>
      </Modal>
    </div>
  );
};
