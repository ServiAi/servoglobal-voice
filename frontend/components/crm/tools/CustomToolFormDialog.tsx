'use client';

import { FormEvent, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Wrench } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CircularLoader } from '@/components/ui/circular-loader';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { createCustomToolAction, updateCustomToolAction } from '@/app/[locale]/(tenant)/voice-ai/tools/actions';
import type { CustomToolAuthType, CustomToolMethod, CustomToolResponse } from '@/types/tools-custom';

type Props = {
  tool: CustomToolResponse | null;
  onClose: () => void;
  onSaved: (tool: CustomToolResponse) => void;
};

const FIELD_CLASS =
  'min-h-10 w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';
const TEXTAREA_CLASS = `${FIELD_CLASS} min-h-24 font-mono text-xs leading-relaxed`;
const METHODS: CustomToolMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const AUTH_TYPES: CustomToolAuthType[] = ['none', 'bearer', 'api_key', 'basic'];
const KNOWN_ERROR_CODES = new Set(['tool_not_found', 'tool_credential_not_configured']);

function parseJsonObject(text: string, fallback: Record<string, unknown>): Record<string, unknown> | null {
  const trimmed = text.trim();
  if (!trimmed) return fallback;
  try {
    const parsed = JSON.parse(trimmed);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null;
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function CustomToolFormDialog({ tool, onClose, onSaved }: Props) {
  const t = useTranslations('crm.tools.form');
  const [key, setKey] = useState(tool?.key ?? 'custom.');
  const [name, setName] = useState(tool?.name ?? '');
  const [description, setDescription] = useState(tool?.description ?? '');
  const [method, setMethod] = useState<CustomToolMethod>(tool?.method ?? 'GET');
  const [baseUrl, setBaseUrl] = useState(tool?.base_url ?? 'https://');
  const [pathTemplate, setPathTemplate] = useState(tool?.path_template ?? '/');
  const [timeoutMs, setTimeoutMs] = useState(tool?.timeout_ms ?? 8000);
  const [headersText, setHeadersText] = useState(JSON.stringify(tool?.headers ?? {}, null, 2));
  const [pathMappingText, setPathMappingText] = useState(JSON.stringify(tool?.path_mapping ?? {}, null, 2));
  const [queryMappingText, setQueryMappingText] = useState(JSON.stringify(tool?.query_mapping ?? {}, null, 2));
  const [bodyMappingText, setBodyMappingText] = useState(JSON.stringify(tool?.body_mapping ?? {}, null, 2));
  const [inputSchemaText, setInputSchemaText] = useState(
    JSON.stringify(tool?.input_schema ?? { type: 'object', properties: {}, required: [] }, null, 2)
  );
  const [responseMappingText, setResponseMappingText] = useState(
    JSON.stringify(tool?.response_mapping ?? {}, null, 2)
  );
  const [authType, setAuthType] = useState<CustomToolAuthType>(tool?.credential.auth_type ?? 'none');
  const [apiKeyHeaderName, setApiKeyHeaderName] = useState(tool?.credential.api_key_header_name ?? 'X-API-Key');
  const [token, setToken] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [jsonFieldError, setJsonFieldError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorCode(null);
    setJsonFieldError(null);

    const headers = parseJsonObject(headersText, {});
    const pathMapping = parseJsonObject(pathMappingText, {});
    const queryMapping = parseJsonObject(queryMappingText, {});
    const bodyMapping = parseJsonObject(bodyMappingText, {});
    const inputSchema = parseJsonObject(inputSchemaText, {});
    const responseMapping = parseJsonObject(responseMappingText, {});

    if (
      headers === null ||
      pathMapping === null ||
      queryMapping === null ||
      bodyMapping === null ||
      inputSchema === null ||
      responseMapping === null
    ) {
      setJsonFieldError(t('errors.invalidJson'));
      return;
    }

    let secrets: Record<string, string> | undefined;
    if (authType === 'bearer' && token) secrets = { token };
    else if (authType === 'api_key' && apiKey) secrets = { api_key: apiKey };
    else if (authType === 'basic' && username && password) secrets = { username, password };

    setBusy(true);
    const result = tool
      ? await updateCustomToolAction(tool.id, {
          name,
          description,
          method,
          base_url: baseUrl,
          path_template: pathTemplate,
          timeout_ms: timeoutMs,
          headers: headers as Record<string, string>,
          path_mapping: pathMapping as Record<string, string>,
          query_mapping: queryMapping as Record<string, string>,
          body_mapping: bodyMapping as Record<string, string>,
          input_schema: inputSchema,
          response_mapping: responseMapping as Record<string, string>,
          auth_type: authType,
          api_key_header_name: authType === 'api_key' ? apiKeyHeaderName : null,
          ...(secrets ? { secrets } : {}),
        })
      : await createCustomToolAction({
          key,
          name,
          description,
          method,
          base_url: baseUrl,
          path_template: pathTemplate,
          timeout_ms: timeoutMs,
          headers: headers as Record<string, string>,
          path_mapping: pathMapping as Record<string, string>,
          query_mapping: queryMapping as Record<string, string>,
          body_mapping: bodyMapping as Record<string, string>,
          input_schema: inputSchema,
          response_mapping: responseMapping as Record<string, string>,
          auth_type: authType,
          api_key_header_name: authType === 'api_key' ? apiKeyHeaderName : null,
          ...(secrets ? { secrets } : {}),
        });

    setBusy(false);
    if (!result.ok) {
      setErrorCode(result.detail);
      return;
    }
    onSaved(result.data);
  };

  const errorMessageKey = errorCode && KNOWN_ERROR_CODES.has(errorCode) ? errorCode : 'generic';

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-2xl grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 sm:max-h-[calc(100dvh-2rem)] sm:w-full">
        <DialogHeader className="border-b border-border bg-muted/30 p-4 pr-12 sm:p-5 sm:pr-12">
          <div className="mb-2 flex size-10 items-center justify-center rounded-md border border-border bg-background text-muted-foreground">
            <Wrench className="size-5" aria-hidden="true" />
          </div>
          <DialogTitle>{tool ? t('editTitle') : t('createTitle')}</DialogTitle>
          <DialogDescription>{t('subtitle')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid min-h-0 grid-rows-[minmax(0,1fr)_auto]">
          <div className="min-h-0 space-y-5 overflow-y-auto overscroll-contain p-4 sm:p-5">
            {errorCode && (
              <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                {t(`errors.${errorMessageKey}`)}
              </p>
            )}
            {jsonFieldError && (
              <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                {jsonFieldError}
              </p>
            )}

            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground">{t('sections.identity')}</h3>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('name')}</span>
                <input className={FIELD_CLASS} value={name} onChange={(e) => setName(e.target.value)} required maxLength={160} />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('key')}</span>
                <input
                  className={FIELD_CLASS}
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  required
                  disabled={!!tool}
                  pattern="custom\.[a-z0-9_]{1,60}"
                  placeholder="custom.customer_balance"
                />
                <span className="block text-xs text-muted-foreground">{t('keyHelp')}</span>
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('description')}</span>
                <textarea
                  className={FIELD_CLASS}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  required
                  maxLength={2000}
                  rows={2}
                />
              </label>
            </section>

            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground">{t('sections.endpoint')}</h3>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="space-y-1 text-sm">
                  <span className="font-medium text-foreground">{t('method')}</span>
                  <select className={FIELD_CLASS} value={method} onChange={(e) => setMethod(e.target.value as CustomToolMethod)}>
                    {METHODS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1 text-sm sm:col-span-2">
                  <span className="font-medium text-foreground">{t('baseUrl')}</span>
                  <input
                    className={FIELD_CLASS}
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    required
                    placeholder="https://api.example.com"
                  />
                </label>
              </div>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('pathTemplate')}</span>
                <input
                  className={FIELD_CLASS}
                  value={pathTemplate}
                  onChange={(e) => setPathTemplate(e.target.value)}
                  placeholder="/customers/{document}/balance"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('timeoutMs')}</span>
                <input
                  type="number"
                  min={1000}
                  max={15000}
                  step={500}
                  className={FIELD_CLASS}
                  value={timeoutMs}
                  onChange={(e) => setTimeoutMs(Number(e.target.value))}
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('headers')}</span>
                <textarea className={TEXTAREA_CLASS} value={headersText} onChange={(e) => setHeadersText(e.target.value)} spellCheck={false} />
              </label>
            </section>

            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground">{t('sections.schema')}</h3>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('inputSchema')}</span>
                <span className="block text-xs text-muted-foreground">{t('inputSchemaHelp')}</span>
                <textarea className={TEXTAREA_CLASS} value={inputSchemaText} onChange={(e) => setInputSchemaText(e.target.value)} spellCheck={false} />
              </label>
            </section>

            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground">{t('sections.mapping')}</h3>
              <span className="block text-xs text-muted-foreground">{t('mappingHelp')}</span>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('pathMapping')}</span>
                <textarea className={TEXTAREA_CLASS} value={pathMappingText} onChange={(e) => setPathMappingText(e.target.value)} spellCheck={false} />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('queryMapping')}</span>
                <textarea className={TEXTAREA_CLASS} value={queryMappingText} onChange={(e) => setQueryMappingText(e.target.value)} spellCheck={false} />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('bodyMapping')}</span>
                <textarea className={TEXTAREA_CLASS} value={bodyMappingText} onChange={(e) => setBodyMappingText(e.target.value)} spellCheck={false} />
              </label>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('responseMapping')}</span>
                <textarea className={TEXTAREA_CLASS} value={responseMappingText} onChange={(e) => setResponseMappingText(e.target.value)} spellCheck={false} />
              </label>
            </section>

            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-foreground">{t('sections.auth')}</h3>
              <label className="space-y-1 text-sm">
                <span className="font-medium text-foreground">{t('authType')}</span>
                <select className={FIELD_CLASS} value={authType} onChange={(e) => setAuthType(e.target.value as CustomToolAuthType)}>
                  {AUTH_TYPES.map((a) => (
                    <option key={a} value={a}>
                      {t(`authOptions.${a}`)}
                    </option>
                  ))}
                </select>
              </label>

              {tool && tool.credential.auth_type !== 'none' && (
                <p className="text-xs text-muted-foreground">
                  {t('currentCredential')}{' '}
                  {tool.credential.configured ? (
                    <span className="font-mono">
                      {Object.values(tool.credential.masked_fields).join(', ') || t('configured')}
                    </span>
                  ) : (
                    t('notConfigured')
                  )}
                </p>
              )}

              {authType === 'bearer' && (
                <label className="space-y-1 text-sm">
                  <span className="font-medium text-foreground">{t('token')}</span>
                  <input
                    type="password"
                    className={FIELD_CLASS}
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder={tool ? t('leaveBlankToKeep') : ''}
                  />
                </label>
              )}
              {authType === 'api_key' && (
                <>
                  <label className="space-y-1 text-sm">
                    <span className="font-medium text-foreground">{t('apiKeyHeaderName')}</span>
                    <input
                      className={FIELD_CLASS}
                      value={apiKeyHeaderName}
                      onChange={(e) => setApiKeyHeaderName(e.target.value)}
                      placeholder="X-API-Key"
                    />
                  </label>
                  <label className="space-y-1 text-sm">
                    <span className="font-medium text-foreground">{t('apiKey')}</span>
                    <input
                      type="password"
                      className={FIELD_CLASS}
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder={tool ? t('leaveBlankToKeep') : ''}
                    />
                  </label>
                </>
              )}
              {authType === 'basic' && (
                <>
                  <label className="space-y-1 text-sm">
                    <span className="font-medium text-foreground">{t('username')}</span>
                    <input className={FIELD_CLASS} value={username} onChange={(e) => setUsername(e.target.value)} />
                  </label>
                  <label className="space-y-1 text-sm">
                    <span className="font-medium text-foreground">{t('password')}</span>
                    <input
                      type="password"
                      className={FIELD_CLASS}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder={tool ? t('leaveBlankToKeep') : ''}
                    />
                  </label>
                </>
              )}
            </section>
          </div>

          <DialogFooter className="border-t border-border bg-background p-4 sm:px-5">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('cancel')}
            </Button>
            <Button type="submit" disabled={busy} className="gap-2">
              {busy && <CircularLoader size="xs" glow={false} />}
              {t('save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
