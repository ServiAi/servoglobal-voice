'use client';

import type { useTranslations } from 'next-intl';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ParameterSpecResponse, VoiceModelResponse, VoiceProviderResponse } from '@/types/voice-registry';

export const FIELD_CLASS =
  'min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground';

/** Renders one control for a single ParameterSpecResponse. The control type
 * is entirely driven by `spec.type` -- there is no per-provider branching
 * here, so a new provider/model automatically gets a working control the
 * moment the Registry declares its parameters. Only `supported: true`
 * parameters ever reach this component (see AgentModelSection below). */
function ParameterControl({
  paramKey,
  spec,
  rawValue,
  disabled,
  onTextChange,
  onBooleanChange,
  t,
}: {
  paramKey: string;
  spec: ParameterSpecResponse;
  rawValue: string;
  disabled: boolean;
  onTextChange: (key: string, value: string) => void;
  onBooleanChange: (key: string, value: boolean) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const label = t(`model.parameters.${paramKey}`);

  if (spec.type === 'boolean') {
    return (
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          disabled={disabled}
          checked={rawValue === 'true'}
          onChange={(e) => onBooleanChange(paramKey, e.target.checked)}
          className="size-4 rounded border-input"
        />
        <span className="font-medium text-foreground">{label}</span>
      </label>
    );
  }

  if (spec.type === 'enum') {
    return (
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">{label}</span>
        <select className={FIELD_CLASS} disabled={disabled} value={rawValue} onChange={(e) => onTextChange(paramKey, e.target.value)}>
          <option value="">{t('model.parameters.useDefault')}</option>
          {(spec.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (spec.type === 'number' || spec.type === 'integer') {
    return (
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">
          {label}
          {spec.min != null && spec.max != null ? ` (${spec.min}–${spec.max})` : ''}
        </span>
        <input
          type="number"
          className={FIELD_CLASS}
          disabled={disabled}
          min={spec.min ?? undefined}
          max={spec.max ?? undefined}
          step={spec.step ?? (spec.type === 'integer' ? 1 : undefined)}
          placeholder={t('model.parameters.useDefault')}
          value={rawValue}
          onChange={(e) => onTextChange(paramKey, e.target.value)}
        />
      </label>
    );
  }

  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="font-medium text-foreground">{label}</span>
      <input className={FIELD_CLASS} disabled={disabled} value={rawValue} onChange={(e) => onTextChange(paramKey, e.target.value)} />
    </label>
  );
}

export function AgentModelSection({
  pipelineType,
  provider,
  model,
  providers,
  models,
  managementMode,
  providerAgentId,
  providerAgentName,
  observedRevisionId,
  currentRevisionId,
  hasBlockingTools,
  modelSettings,
  disabled,
  onManagementModeChange,
  onProviderChange,
  onModelChange,
  onModelSettingTextChange,
  onModelSettingBooleanChange,
  t,
}: {
  pipelineType: 'realtime';
  provider: string;
  model: string;
  providers: VoiceProviderResponse[];
  models: VoiceModelResponse[];
  managementMode: 'serviglobal_managed' | 'provider_managed';
  providerAgentId: string;
  providerAgentName: string;
  observedRevisionId: string;
  currentRevisionId: string | null;
  hasBlockingTools: boolean;
  modelSettings: Record<string, string>;
  disabled: boolean;
  onManagementModeChange: (value: 'serviglobal_managed' | 'provider_managed') => void;
  onProviderChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onModelSettingTextChange: (key: string, value: string) => void;
  onModelSettingBooleanChange: (key: string, value: boolean) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const realtimeModels = models.filter((m) => m.model_type === 'realtime' && m.provider_key === provider);
  const selectedModel = models.find((m) => m.provider_key === provider && m.key === model) ?? null;
  const activeCapabilities = selectedModel
    ? Object.entries(selectedModel.capabilities).filter(([, enabled]) => enabled)
    : [];
  // Capability-driven: only parameters the Registry marks supported=true for
  // the currently selected model ever render a control. A model with no
  // supported parameters simply shows no "Parámetros" block.
  const supportedParameters = selectedModel
    ? Object.entries(selectedModel.parameters).filter(([, spec]) => spec.supported)
    : [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('voice.pipelineType')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              pipelineType === 'realtime'
                ? 'bg-primary text-primary-foreground'
                : 'border border-dashed border-border text-muted-foreground'
            }`}
          >
            {t('voice.speechToSpeech')}
          </span>
          <span className="rounded-full border border-dashed border-border px-3 py-1 text-xs text-muted-foreground">
            {t('voice.modular')} · {t('voice.comingSoon')}
          </span>
          <span className="rounded-full border border-dashed border-border px-3 py-1 text-xs text-muted-foreground">
            {t('voice.hybrid')} · {t('voice.comingSoon')}
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('providerManaged.title')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-foreground">{t('providerManaged.source')}</span>
            <select
              className={FIELD_CLASS}
              disabled={disabled || Boolean(providerAgentId)}
              value={managementMode}
              onChange={(event) => onManagementModeChange(event.target.value as 'serviglobal_managed' | 'provider_managed')}
            >
              <option value="serviglobal_managed">{t('providerManaged.serviglobal')}</option>
              <option value="provider_managed" disabled={!providerAgentId}>{t('providerManaged.ultravox')}</option>
            </select>
          </label>
          {managementMode === 'provider_managed' ? (
            <div className="rounded-lg border border-cyan-500/30 bg-cyan-500/5 p-4 text-sm">
              <p className="font-medium">{providerAgentName || providerAgentId}</p>
              <p className="mt-1 text-muted-foreground">{t('providerManaged.remoteId', { id: providerAgentId })}</p>
              <p className="text-muted-foreground">{t('providerManaged.revision', { revision: observedRevisionId || t('providerManaged.unpublished') })}</p>
              {currentRevisionId && observedRevisionId && currentRevisionId !== observedRevisionId ? <p className="mt-2 font-medium text-amber-700">{t('providerManaged.drift', { revision: currentRevisionId })}</p> : null}
              {hasBlockingTools ? <p className="mt-2 font-medium text-destructive">{t('providerManaged.blockedTools')}</p> : null}
              <p className="mt-2 text-xs text-muted-foreground">{t('providerManaged.help')}</p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('voice.providerModel')}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-foreground">{t('voice.provider')}</span>
            <select
              className={FIELD_CLASS}
              disabled={disabled || managementMode === 'provider_managed'}
              value={provider}
              onChange={(e) => onProviderChange(e.target.value)}
            >
              {providers.map((p) => (
                <option key={p.key} value={p.key} disabled={p.status !== 'active'}>
                  {p.name}
                  {p.status !== 'active' ? ` (${t('voice.comingSoon')})` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-foreground">{t('voice.model')}</span>
            <select
              className={FIELD_CLASS}
              disabled={disabled || managementMode === 'provider_managed' || realtimeModels.length === 0}
              value={model}
              onChange={(e) => onModelChange(e.target.value)}
            >
              {realtimeModels.length === 0 ? (
                <option value="">{t('voice.noModels')}</option>
              ) : (
                realtimeModels.map((m) => (
                  <option key={m.id} value={m.key} disabled={m.implementation_status !== 'available'}>
                    {m.name}
                    {m.implementation_status !== 'available' ? ` (${t('voice.comingSoon')})` : ''}
                  </option>
                ))
              )}
            </select>
          </label>
        </CardContent>
        {activeCapabilities.length > 0 ? (
          <CardContent className="flex flex-wrap gap-2 pt-0">
            {activeCapabilities.map(([key]) => (
              <span
                key={key}
                className="rounded-full bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-700 dark:text-cyan-300"
              >
                {t(`voice.capabilities.${key}`)}
              </span>
            ))}
          </CardContent>
        ) : null}
      </Card>

      {managementMode === 'serviglobal_managed' && supportedParameters.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('model.parametersTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            {supportedParameters.map(([key, spec]) => (
              <ParameterControl
                key={key}
                paramKey={key}
                spec={spec}
                rawValue={modelSettings[key] ?? ''}
                disabled={disabled}
                onTextChange={onModelSettingTextChange}
                onBooleanChange={onModelSettingBooleanChange}
                t={t}
              />
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
