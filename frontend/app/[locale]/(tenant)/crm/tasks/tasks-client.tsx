'use client';

import React, { useState, useTransition, useCallback } from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import type { TaskResponse } from '@/types/crm';
import { CrmTaskList } from '@/components/crm/CrmTaskList';
import { CrmTaskForm } from '@/components/crm/CrmTaskForm';
import { createCrmTask, updateCrmTask, deleteCrmTask } from '@/lib/api/crm';
import { ShieldAlert, Filter, CheckSquare } from 'lucide-react';
import { CircularLoader } from '@/components/ui/circular-loader';
import { useTranslations } from 'next-intl';

type TasksClientProps = {
  tasks: TaskResponse[];
  accessToken: string;
  locale: string;
  userRole?: string;
};

export function TasksClient({
  tasks,
  accessToken,
  locale,
  userRole,
}: TasksClientProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const t = useTranslations('crm.tasks');
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filter states
  const [status, setStatus] = useState(searchParams.get('status') || '');
  const [priority, setPriority] = useState(searchParams.get('priority') || '');

  const triggerRefresh = (msg: string) => {
    setSuccessMsg(msg);
    startTransition(() => {
      router.refresh();
    });
    setTimeout(() => setSuccessMsg(null), 3000);
  };

  const createQueryString = useCallback(
    (params: Record<string, string>) => {
      const newSearchParams = new URLSearchParams(searchParams.toString());
      Object.entries(params).forEach(([name, value]) => {
        if (value) {
          newSearchParams.set(name, value);
        } else {
          newSearchParams.delete(name);
        }
      });
      return newSearchParams.toString();
    },
    [searchParams]
  );

  const handleApplyFilters = (e: React.FormEvent) => {
    e.preventDefault();
    router.push(`${pathname}?${createQueryString({ status, priority })}`);
  };

  const handleResetFilters = () => {
    setStatus('');
    setPriority('');
    router.push(pathname);
  };

  const handleCreateTask = async (taskPayload: {
    title: string;
    description?: string;
    due_at?: string;
    priority: string;
  }) => {
    setError(null);
    const res = await createCrmTask(accessToken, taskPayload);
    if (res.ok) {
      triggerRefresh(t('created'));
    } else {
      setError(t('createError', { detail: res.detail }));
      throw new Error(res.detail);
    }
  };

  const handleToggleTaskStatus = async (taskId: string, nextStatus: string) => {
    setError(null);
    const res = await updateCrmTask(accessToken, taskId, { status: nextStatus });
    if (res.ok) {
      triggerRefresh(t('updated'));
    } else {
      setError(t('updateError', { detail: res.detail }));
    }
  };

  const handleDeleteTask = async (taskId: string) => {
    setError(null);
    const res = await deleteCrmTask(accessToken, taskId);
    if (res.ok) {
      triggerRefresh(t('deleted'));
    } else {
      setError(t('deleteError', { detail: res.detail }));
    }
  };

  const pendingCount = tasks.filter((t) => t.status === 'pending').length;
  const completedCount = tasks.filter((t) => t.status === 'done').length;
  const today = new Date();
  const todayKey = today.toDateString();
  const openTasks = tasks.filter((task) => task.status !== 'done');
  const overdueCount = openTasks.filter((task) => task.due_at && new Date(task.due_at) < today && new Date(task.due_at).toDateString() !== todayKey).length;
  const todayCount = openTasks.filter((task) => task.due_at && new Date(task.due_at).toDateString() === todayKey).length;
  const upcomingCount = openTasks.filter((task) => task.due_at && new Date(task.due_at) > today && new Date(task.due_at).toDateString() !== todayKey).length;
  const undatedCount = openTasks.filter((task) => !task.due_at).length;

  return (
    <div className="flex flex-col gap-6">
      {/* Toast Alert Feedback */}
      {(error || successMsg || isPending) && (
        <div className="fixed bottom-5 right-5 z-50 max-w-sm rounded-lg border bg-card p-4 shadow-lg transition-all duration-300">
          {isPending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <CircularLoader size="xs" glow={false} />
              <span>{t('syncing')}</span>
            </div>
          )}
          {error && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <ShieldAlert className="h-4 w-4" />
              <span>{error}</span>
            </div>
          )}
          {successMsg && !isPending && (
            <div className="flex items-center gap-2 text-sm text-emerald-500">
              <div className="h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
              <span>{successMsg}</span>
            </div>
          )}
        </div>
      )}

      {/* Header section */}
      <section className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold tracking-tight text-foreground">
          {t('title')}
        </h2>
        <p className="text-sm text-muted-foreground">
          {t('description')}
        </p>
      </section>

      <section aria-label={t('temporalSummary')} className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          [t('overdue'), overdueCount, 'text-destructive'],
          [t('today'), todayCount, 'text-amber-600 dark:text-amber-400'],
          [t('upcoming'), upcomingCount, 'text-primary'],
          [t('undated'), undatedCount, 'text-muted-foreground'],
        ].map(([label, value, tone]) => (
          <div key={label} className="rounded-xl border border-border bg-card p-4 shadow-xs">
            <p className="text-sm font-medium text-muted-foreground">{label}</p>
            <p className={`mt-1 text-2xl font-bold ${tone}`}>{value}</p>
          </div>
        ))}
      </section>

      {/* Grid: Filters & Creation vs Tasks List */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Side: Filters & Creation (1 col) */}
        <div className="lg:col-span-1 flex flex-col gap-6">
          {/* Filters Form */}
          <div className="rounded-xl border border-border bg-card p-4 shadow-xs sm:p-5 flex flex-col gap-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground pb-3 border-b border-border">
              <Filter className="h-4 w-4 text-primary" />
              <span>{t('filters')}</span>
            </div>

            <form onSubmit={handleApplyFilters} className="flex flex-col gap-4">
              <div className="flex flex-col gap-1">
                <label htmlFor="filter-status" className="text-sm font-medium text-foreground">
                  {t('status')}
                </label>
                <select
                  id="filter-status"
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  className="min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="">{t('all')}</option>
                  <option value="pending">{t('pending')}</option>
                  <option value="done">{t('completed')}</option>
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <label htmlFor="filter-priority" className="text-sm font-medium text-foreground">
                  {t('priority')}
                </label>
                <select
                  id="filter-priority"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                  className="min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="">{t('allPriorities')}</option>
                  <option value="high">{t('high')}</option>
                  <option value="medium">{t('medium')}</option>
                  <option value="low">{t('low')}</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/40">
                <button
                  type="button"
                  onClick={handleResetFilters}
                  className="min-h-11 rounded-md border border-border px-3 py-2 text-sm font-semibold text-muted-foreground hover:bg-muted"
                >
                  {t('clear')}
                </button>
                <button
                  type="submit"
                  className="min-h-11 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
                >
                  {t('apply')}
                </button>
              </div>
            </form>
          </div>

          {/* Creation Form */}
          <CrmTaskForm onSubmit={handleCreateTask} userRole={userRole} />
        </div>

        {/* Right Side: Tasks List (2 cols) */}
        <div className="lg:col-span-2 flex flex-col gap-4">
          <div className="rounded-xl border border-border bg-card p-4 shadow-xs sm:p-6 flex flex-col gap-4">
            <div className="border-b border-border/60 pb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckSquare className="h-5 w-5 text-primary" />
                <h3 className="text-base font-bold text-foreground">{t('list')}</h3>
              </div>
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground font-semibold">
                <span className="text-amber-500">{t('pendingCount', { count: pendingCount })}</span>
                <span aria-hidden="true">•</span>
                <span className="text-emerald-500">{t('completedCount', { count: completedCount })}</span>
              </div>
            </div>

            <CrmTaskList
              tasks={tasks}
              onToggleStatus={handleToggleTaskStatus}
              onDelete={handleDeleteTask}
              showLeadInfo={true}
              userRole={userRole}
              locale={locale}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
