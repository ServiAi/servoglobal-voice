'use client';

import { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle2, Phone, Plus, Edit2, RotateCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FieldHelp } from './FieldHelp';
import type {
  VoiceProviderConfigRequest,
  VoiceProviderConfigResponse,
  VoiceAgentConfigRequest,
  VoiceAgentConfigResponse,
} from '@/types/crm';
import {
  fetchVoiceConfig,
  configureVoice,
  testVoiceConnection,
  fetchVoiceAgents,
  createVoiceAgent,
  updateVoiceAgent,
  fetchAdminTenantVoiceConfig,
  configureAdminTenantVoice,
  testAdminTenantVoice,
  fetchAdminTenantVoiceAgents,
  createAdminTenantVoiceAgent,
  updateAdminTenantVoiceAgent,
} from '@/lib/api/crm';

type Props = {
  accessToken: string;
  initialConfig?: VoiceProviderConfigResponse;
  initialAgents?: VoiceAgentConfigResponse[];
  mode?: 'tenant' | 'admin';
  tenantId?: string;
};

export function VoiceIntegrationCard({
  accessToken,
  initialConfig,
  initialAgents = [],
  mode = 'tenant',
  tenantId,
}: Props) {
  const [config, setConfig] = useState<VoiceProviderConfigResponse | undefined>(initialConfig);
  const [agents, setAgents] = useState<VoiceAgentConfigResponse[]>(initialAgents);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [testing, setTesting] = useState(false);

  // Agent form state
  const [editingAgent, setEditingAgent] = useState<VoiceAgentConfigResponse | null>(null);
  const [showAgentForm, setShowAgentForm] = useState(false);
  const [savingAgent, setSavingAgent] = useState(false);

  const [agentForm, setAgentForm] = useState<VoiceAgentConfigRequest>({
    provider_agent_id: '',
    display_name: '',
    description: '',
    purpose: 'Atención al Cliente',
    default_language: 'es',
    default_timezone: 'America/Bogota',
    default_voice: 'standard-female',
    status: 'active',
  });

  const [configForm, setConfigForm] = useState<VoiceProviderConfigRequest>({
    provider: 'ultravox',
    display_name: config?.display_name ?? 'Ultravox Voice Service',
    base_url: config?.base_url ?? 'https://api.ultravox.ai',
    default_voice_agent_id: config?.default_voice_agent_id ?? '',
    default_from_number: config?.default_from_number ?? '',
    default_language: config?.default_language ?? 'es',
    default_timezone: config?.default_timezone ?? 'America/Bogota',
    status: config?.status ?? 'active',
  });

  const isActive = config?.status === 'active';

  const notify = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  // Load agents on mount if not provided or empty
  useEffect(() => {
    async function load() {
      setLoadingAgents(true);
      const res =
        mode === 'admin' && tenantId
          ? await fetchAdminTenantVoiceAgents(accessToken, tenantId)
          : await fetchVoiceAgents(accessToken);
      setLoadingAgents(false);
      if (res.ok) {
        setAgents(res.data);
      }
    }
    load();
  }, [accessToken, mode, tenantId]);

  const updateConfigField = (key: keyof VoiceProviderConfigRequest, value: string) => {
    setConfigForm((curr) => ({ ...curr, [key]: value }));
  };

  const handleSaveConfig = async () => {
    setSavingConfig(true);
    const payload = {
      ...configForm,
      api_key: configForm.api_key?.trim() || null,
      webhook_secret: configForm.webhook_secret?.trim() || null,
    };
    const result =
      mode === 'admin' && tenantId
        ? await configureAdminTenantVoice(accessToken, tenantId, payload)
        : await configureVoice(accessToken, payload);
    setSavingConfig(false);

    if (!result.ok) {
      notify('error', result.detail);
      return;
    }
    setConfig(result.data);
    notify('success', 'Configuración de proveedor de voz guardada exitosamente.');
  };

  const handleTestConnection = async () => {
    setTesting(true);
    const result =
      mode === 'admin' && tenantId
        ? await testAdminTenantVoice(accessToken, tenantId)
        : await testVoiceConnection(accessToken);
    setTesting(false);

    if (!result.ok) {
      notify('error', `Error en la conexión: ${result.detail}`);
      return;
    }
    notify('success', 'La prueba de conexión fue exitosa. Servidor activo.');
  };

  const handleAddAgentClick = () => {
    setEditingAgent(null);
    setAgentForm({
      provider_agent_id: '',
      display_name: '',
      description: '',
      purpose: 'Atención al Cliente',
      default_language: 'es',
      default_timezone: 'America/Bogota',
      default_voice: 'standard-female',
      status: 'active',
    });
    setShowAgentForm(true);
  };

  const handleEditAgentClick = (agent: VoiceAgentConfigResponse) => {
    setEditingAgent(agent);
    setAgentForm({
      provider_agent_id: agent.provider_agent_id,
      display_name: agent.display_name,
      description: agent.description,
      purpose: agent.purpose,
      default_language: agent.default_language,
      default_timezone: agent.default_timezone,
      default_voice: agent.default_voice,
      status: agent.status,
    });
    setShowAgentForm(true);
  };

  const handleSaveAgent = async () => {
    if (!agentForm.provider_agent_id.trim()) {
      notify('error', 'El Agent ID del proveedor es obligatorio.');
      return;
    }
    if (!agentForm.display_name.trim()) {
      notify('error', 'El nombre para mostrar es obligatorio.');
      return;
    }

    setSavingAgent(true);
    const payload = {
      ...agentForm,
      provider_config_id: config?.id || null,
      provider: 'ultravox',
    };

    const result = editingAgent
      ? mode === 'admin' && tenantId
        ? await updateAdminTenantVoiceAgent(accessToken, tenantId, editingAgent.id, payload)
        : await updateVoiceAgent(accessToken, editingAgent.id, payload)
      : mode === 'admin' && tenantId
      ? await createAdminTenantVoiceAgent(accessToken, tenantId, payload)
      : await createVoiceAgent(accessToken, payload);

    setSavingAgent(false);

    if (!result.ok) {
      notify('error', result.detail);
      return;
    }

    // Refresh agent list
    const listRes =
      mode === 'admin' && tenantId
        ? await fetchAdminTenantVoiceAgents(accessToken, tenantId)
        : await fetchVoiceAgents(accessToken);
    if (listRes.ok) {
      setAgents(listRes.data);
    }

    setShowAgentForm(false);
    setEditingAgent(null);
    notify('success', `Agente de voz ${editingAgent ? 'actualizado' : 'creado'} exitosamente.`);
  };

  return (
    <section className="rounded-xl border border-border bg-card p-6 shadow-xs">
      <div className="mb-5 flex flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-indigo-500/10 text-indigo-500">
            <Phone className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold text-foreground">Agentes de Voz AI</h2>
            <p className="text-sm text-muted-foreground">
              Configuración de telefonía y agentes virtuales (Ultravox / PBX)
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-2 rounded-md border px-3 py-1 text-xs font-semibold ${
              isActive ? 'border-emerald-500/30 text-emerald-500' : 'border-amber-500/30 text-amber-500'
            }`}
          >
            {isActive ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
            {isActive ? 'activo' : config?.status ?? 'no configurado'}
          </span>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Left Side: Provider Credentials Config */}
        <div className="md:col-span-1 space-y-4 border-r border-border pr-0 md:pr-6">
          <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider">
            Proveedor e Integración
          </h3>
          <div className="space-y-3">
            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              <span className="flex items-center gap-1">Nombre descriptivo <FieldHelp label="Nombre descriptivo de voz" required={false}>Es un nombre interno para reconocer esta configuración; no se obtiene del proveedor.</FieldHelp></span>
              <input
                type="text"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-ring"
                value={configForm.display_name ?? ''}
                onChange={(e) => updateConfigField('display_name', e.target.value)}
              />
            </label>

            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              <span className="flex items-center gap-1">Ultravox API Key <FieldHelp label="Ultravox API Key" required={!config?.has_secret}>Créala en el panel de Ultravox → Settings → API Keys. Solo es obligatoria la primera vez.</FieldHelp></span>
              <input
                type="password"
                placeholder={config?.has_secret ? '••••••••••••••••••••' : 'uvx_api_...'}
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-ring"
                onChange={(e) => updateConfigField('api_key', e.target.value)}
              />
            </label>

            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              <span className="flex items-center gap-1">Webhook Secret (Firma) <FieldHelp label="Webhook Secret" required={false}>Créalo como una cadena secreta y configura el mismo valor en el webhook del proveedor.</FieldHelp></span>
              <input
                type="password"
                placeholder={config?.has_webhook_secret ? '••••••••••••••••••••' : 'Secreto opcional'}
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-ring"
                onChange={(e) => updateConfigField('webhook_secret', e.target.value)}
              />
            </label>

            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              <span className="flex items-center gap-1">Base URL Proveedor <FieldHelp label="Base URL Proveedor" required>Usa la URL base oficial del proveedor; para Ultravox es https://api.ultravox.ai.</FieldHelp></span>
              <input
                type="text"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-ring"
                value={configForm.base_url ?? ''}
                onChange={(e) => updateConfigField('base_url', e.target.value)}
              />
            </label>

            <div className="grid grid-cols-2 gap-2">
              <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                <span className="flex items-center gap-1">Default Agent ID <FieldHelp label="Default Agent ID" required={false}>Copia el ID del agente predeterminado desde el panel de Ultravox. Puede quedar vacío si se selecciona por otra regla.</FieldHelp></span>
                <input
                  type="text"
                  placeholder="ID de agente por defecto"
                  className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-ring"
                  value={configForm.default_voice_agent_id ?? ''}
                  onChange={(e) => updateConfigField('default_voice_agent_id', e.target.value)}
                />
              </label>

              <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                <span className="flex items-center gap-1">Outgoing Number (SIP) <FieldHelp label="Outgoing Number SIP" required={false}>Es el número saliente asignado por tu operador SIP/PBX, en formato internacional.</FieldHelp></span>
                <input
                  type="text"
                  placeholder="+57..."
                  className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-ring"
                  value={configForm.default_from_number ?? ''}
                  onChange={(e) => updateConfigField('default_from_number', e.target.value)}
                />
              </label>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                <span className="flex items-center gap-1">Idioma <FieldHelp label="Idioma predeterminado de voz" required>Selecciona el idioma principal que usará la integración.</FieldHelp></span>
                <select
                  className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-ring"
                  value={configForm.default_language}
                  onChange={(e) => updateConfigField('default_language', e.target.value)}
                >
                  <option value="es">Español</option>
                  <option value="en">Inglés</option>
                </select>
              </label>

              <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                <span className="flex items-center gap-1">Zona horaria <FieldHelp label="Zona horaria de voz" required>Usa una zona IANA como America/Bogota para interpretar horarios correctamente.</FieldHelp></span>
                <input
                  type="text"
                  className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-ring"
                  value={configForm.default_timezone}
                  onChange={(e) => updateConfigField('default_timezone', e.target.value)}
                />
              </label>
            </div>

            <label className="grid gap-1 text-xs font-medium text-muted-foreground">
              <span className="flex items-center gap-1">Estado de Integración <FieldHelp label="Estado de integración de voz" required>Activa la integración solo cuando las credenciales y la conexión estén listas.</FieldHelp></span>
              <select
                className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-hidden focus:ring-1 focus:ring-ring"
                value={configForm.status}
                onChange={(e) => updateConfigField('status', e.target.value)}
              >
                <option value="active">Activo</option>
                <option value="inactive">Inactivo</option>
              </select>
            </label>

            <div className="flex gap-2 pt-2">
              <Button
                type="button"
                onClick={handleSaveConfig}
                disabled={savingConfig}
                className="w-full text-xs"
              >
                {savingConfig ? 'Guardando...' : 'Guardar Config'}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={handleTestConnection}
                disabled={testing || !config?.has_secret}
                className="w-full text-xs"
              >
                {testing ? <RotateCw className="h-3 w-3 animate-spin mr-1" /> : null}
                Probar
              </Button>
            </div>
          </div>
        </div>

        {/* Right Side: Agents Management list */}
        <div className="md:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground uppercase tracking-wider">
              Agentes Configurados
            </h3>
            {!showAgentForm && (
              <Button
                type="button"
                size="sm"
                onClick={handleAddAgentClick}
                className="h-8 text-xs flex items-center gap-1"
              >
                <Plus className="h-3.5 w-3.5" /> Agregar Agente
              </Button>
            )}
          </div>

          {showAgentForm ? (
            <div className="rounded-lg border border-border bg-muted/40 p-4 space-y-3">
              <h4 className="text-xs font-semibold text-foreground uppercase">
                {editingAgent ? 'Editar Agente de Voz' : 'Nuevo Agente de Voz'}
              </h4>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Provider Agent ID * <FieldHelp label="Provider Agent ID" required>Copia el ID único del agente desde el panel del proveedor de voz.</FieldHelp></span>
                  <input
                    type="text"
                    placeholder="wk-xxxx..."
                    className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    value={agentForm.provider_agent_id}
                    onChange={(e) => setAgentForm((curr) => ({ ...curr, provider_agent_id: e.target.value }))}
                  />
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Nombre descriptivo * <FieldHelp label="Nombre descriptivo del agente" required>Escribe un nombre interno que permita identificar el agente dentro del CRM.</FieldHelp></span>
                  <input
                    type="text"
                    placeholder="Ej. Agente Comercial"
                    className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    value={agentForm.display_name}
                    onChange={(e) => setAgentForm((curr) => ({ ...curr, display_name: e.target.value }))}
                  />
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground sm:col-span-2">
                  <span className="flex items-center gap-1">Descripción <FieldHelp label="Descripción del agente" required={false}>Resume el objetivo del agente para que el equipo pueda reconocerlo.</FieldHelp></span>
                  <input
                    type="text"
                    placeholder="Objetivo principal del agente virtual"
                    className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    value={agentForm.description ?? ''}
                    onChange={(e) => setAgentForm((curr) => ({ ...curr, description: e.target.value }))}
                  />
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Caso de Uso / Propósito <FieldHelp label="Caso de uso del agente" required>Selecciona la función comercial principal que cumplirá el agente.</FieldHelp></span>
                  <select
                    className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    value={agentForm.purpose}
                    onChange={(e) => setAgentForm((curr) => ({ ...curr, purpose: e.target.value }))}
                  >
                    <option value="Atención al Cliente">Atención al Cliente</option>
                    <option value="Call Centers y Soporte Técnico">Soporte Técnico</option>
                    <option value="Cobranza y Recuperación de Pagos">Cobranza</option>
                    <option value="Ventas y Generación de Leads">Ventas</option>
                    <option value="Reclutamiento y Selección">Reclutamiento</option>
                    <option value="Reservaciones y Agendamiento">Agendamiento</option>
                    <option value="E-commerce y Tiendas Online">E-commerce</option>
                  </select>
                </label>

                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  <span className="flex items-center gap-1">Voz por defecto <FieldHelp label="Voz por defecto" required={false}>Copia el identificador de voz admitido por el proveedor; si se omite se usa su voz predeterminada.</FieldHelp></span>
                  <input
                    type="text"
                    placeholder="Ej. standard-female"
                    className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                    value={agentForm.default_voice ?? ''}
                    onChange={(e) => setAgentForm((curr) => ({ ...curr, default_voice: e.target.value }))}
                  />
                </label>

                <div className="grid grid-cols-2 gap-2 sm:col-span-2">
                  <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                    <span className="flex items-center gap-1">Idioma <FieldHelp label="Idioma del agente" required>Selecciona el idioma principal del agente.</FieldHelp></span>
                    <select
                      className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                      value={agentForm.default_language}
                      onChange={(e) => setAgentForm((curr) => ({ ...curr, default_language: e.target.value }))}
                    >
                      <option value="es">Español</option>
                      <option value="en">Inglés</option>
                    </select>
                  </label>

                  <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                    <span className="flex items-center gap-1">Estado agente <FieldHelp label="Estado del agente" required>Selecciona Activo cuando el agente esté listo para usarse.</FieldHelp></span>
                    <select
                      className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                      value={agentForm.status}
                      onChange={(e) => setAgentForm((curr) => ({ ...curr, status: e.target.value }))}
                    >
                      <option value="active">Activo</option>
                      <option value="inactive">Inactivo</option>
                    </select>
                  </label>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-border mt-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowAgentForm(false)}
                  className="text-xs"
                >
                  Cancelar
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={handleSaveAgent}
                  disabled={savingAgent}
                  className="text-xs"
                >
                  {savingAgent ? 'Guardando...' : 'Guardar Agente'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-2">
              {loadingAgents ? (
                <div className="text-center py-6 text-sm text-muted-foreground">
                  Cargando lista de agentes de voz...
                </div>
              ) : agents.length === 0 ? (
                <div className="text-center py-8 rounded-lg border border-dashed border-border text-sm text-muted-foreground bg-muted/20">
                  No hay agentes de voz registrados para este tenant.
                </div>
              ) : (
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-muted border-b border-border font-medium text-muted-foreground">
                        <th className="p-3">Nombre</th>
                        <th className="p-3">Propósito</th>
                        <th className="p-3">Provider ID</th>
                        <th className="p-3">Voz</th>
                        <th className="p-3">Estado</th>
                        <th className="p-3 text-right">Acciones</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border bg-card">
                      {agents.map((agent) => (
                        <tr key={agent.id} className="hover:bg-muted/30">
                          <td className="p-3 font-medium text-foreground">
                            {agent.display_name}
                            {agent.description && (
                              <div className="text-[10px] text-muted-foreground font-normal">
                                {agent.description}
                              </div>
                            )}
                          </td>
                          <td className="p-3 text-muted-foreground">{agent.purpose}</td>
                          <td className="p-3 font-mono text-[10px]">{agent.provider_agent_id}</td>
                          <td className="p-3 font-mono text-[10px]">{agent.default_voice || 'default'}</td>
                          <td className="p-3">
                            <span
                              className={`inline-flex px-1.5 py-0.5 rounded-full text-[10px] font-medium border ${
                                agent.status === 'active'
                                  ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-600'
                                  : 'border-amber-500/20 bg-amber-500/10 text-amber-600'
                              }`}
                            >
                              {agent.status}
                            </span>
                          </td>
                          <td className="p-3 text-right">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              onClick={() => handleEditAgentClick(agent)}
                            >
                              <Edit2 className="h-3 w-3" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {config?.last_error_message && (
        <div className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-500">
          <strong>Último error de conexión:</strong> {config.last_error_message}
        </div>
      )}

      {message && (
        <div
          className={`mt-4 rounded-md border p-3 text-sm ${
            message.type === 'success'
              ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-500'
              : 'border-red-500/20 bg-red-500/10 text-red-500'
          }`}
        >
          {message.text}
        </div>
      )}
    </section>
  );
}
