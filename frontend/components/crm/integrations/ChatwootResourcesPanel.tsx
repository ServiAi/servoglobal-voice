'use client';

import { useEffect, useState } from 'react';
import { Check, Loader2, Pencil, Plus, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ChatwootAgentSummary, ChatwootInboxSummary, ChatwootTeamSummary } from '@/types/crm';
import {
  fetchChatwootInboxes,
  fetchAdminTenantChatwootInboxes,
  createChatwootInbox,
  createAdminTenantChatwootInbox,
  updateChatwootInbox,
  updateAdminTenantChatwootInbox,
  fetchChatwootTeams,
  fetchAdminTenantChatwootTeams,
  createChatwootTeam,
  createAdminTenantChatwootTeam,
  updateChatwootTeam,
  updateAdminTenantChatwootTeam,
  deleteChatwootTeam,
  deleteAdminTenantChatwootTeam,
  fetchChatwootAgents,
  fetchAdminTenantChatwootAgents,
  inviteChatwootAgent,
  inviteAdminTenantChatwootAgent,
  updateChatwootAgent,
  updateAdminTenantChatwootAgent,
  deleteChatwootAgent,
  deleteAdminTenantChatwootAgent,
} from '@/lib/api/crm';

type Props = {
  accessToken: string;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onNotify: (type: 'success' | 'error', text: string) => void;
};

const FIELD_CLASS = 'min-h-9 w-full min-w-0 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';
const ICON_BTN_CLASS = 'h-6 w-6 shrink-0';

export function ChatwootResourcesPanel({ accessToken, mode = 'tenant', tenantId, onNotify }: Props) {
  const [inboxes, setInboxes] = useState<ChatwootInboxSummary[]>([]);
  const [teams, setTeams] = useState<ChatwootTeamSummary[]>([]);
  const [agents, setAgents] = useState<ChatwootAgentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const [newInboxName, setNewInboxName] = useState('');
  const [creatingInbox, setCreatingInbox] = useState(false);
  const [editingInboxId, setEditingInboxId] = useState<number | null>(null);
  const [editingInboxName, setEditingInboxName] = useState('');

  const [newTeamName, setNewTeamName] = useState('');
  const [newTeamDescription, setNewTeamDescription] = useState('');
  const [creatingTeam, setCreatingTeam] = useState(false);
  const [editingTeamId, setEditingTeamId] = useState<number | null>(null);
  const [editingTeamName, setEditingTeamName] = useState('');

  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentEmail, setNewAgentEmail] = useState('');
  const [newAgentRole, setNewAgentRole] = useState<'agent' | 'administrator'>('agent');
  const [invitingAgent, setInvitingAgent] = useState(false);
  const [editingAgentId, setEditingAgentId] = useState<number | null>(null);
  const [editingAgentName, setEditingAgentName] = useState('');
  const [editingAgentRole, setEditingAgentRole] = useState<'agent' | 'administrator'>('agent');

  useEffect(() => {
    async function load() {
      setLoading(true);
      const [inboxesRes, teamsRes, agentsRes] =
        mode === 'admin' && tenantId
          ? await Promise.all([
              fetchAdminTenantChatwootInboxes(accessToken, tenantId),
              fetchAdminTenantChatwootTeams(accessToken, tenantId),
              fetchAdminTenantChatwootAgents(accessToken, tenantId),
            ])
          : await Promise.all([
              fetchChatwootInboxes(accessToken),
              fetchChatwootTeams(accessToken),
              fetchChatwootAgents(accessToken),
            ]);
      setLoading(false);
      if (inboxesRes.ok) {
        setInboxes(inboxesRes.data);
      } else {
        onNotify('error', `No se pudieron cargar los inboxes: ${inboxesRes.detail}`);
      }
      if (teamsRes.ok) {
        setTeams(teamsRes.data);
      } else {
        onNotify('error', `No se pudieron cargar los teams: ${teamsRes.detail}`);
      }
      if (agentsRes.ok) {
        setAgents(agentsRes.data);
      } else {
        onNotify('error', `No se pudieron cargar los agentes: ${agentsRes.detail}`);
      }
    }
    load();
    // onNotify is redefined on every render of the parent (not memoized);
    // including it would refetch on every notification instead of only
    // when the tenant/mode actually changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, mode, tenantId]);

  const handleCreateInbox = async () => {
    const name = newInboxName.trim();
    if (!name) return;
    setCreatingInbox(true);
    const result =
      mode === 'admin' && tenantId
        ? await createAdminTenantChatwootInbox(accessToken, tenantId, { name })
        : await createChatwootInbox(accessToken, { name });
    setCreatingInbox(false);
    if (!result.ok) {
      onNotify('error', result.detail);
      return;
    }
    setInboxes((curr) => [...curr, result.data]);
    setNewInboxName('');
    onNotify('success', `Inbox "${result.data.name}" creado.`);
  };

  const startEditInbox = (inbox: ChatwootInboxSummary) => {
    setEditingInboxId(inbox.id);
    setEditingInboxName(inbox.name);
  };

  const handleSaveInbox = async (inboxId: number) => {
    const name = editingInboxName.trim();
    if (!name) return;
    const key = `inbox-${inboxId}`;
    setBusyKey(key);
    const result =
      mode === 'admin' && tenantId
        ? await updateAdminTenantChatwootInbox(accessToken, tenantId, inboxId, { name })
        : await updateChatwootInbox(accessToken, inboxId, { name });
    setBusyKey(null);
    if (!result.ok) {
      onNotify('error', result.detail);
      return;
    }
    setInboxes((curr) => curr.map((i) => (i.id === inboxId ? result.data : i)));
    setEditingInboxId(null);
    onNotify('success', 'Inbox renombrado.');
  };

  const handleCreateTeam = async () => {
    const name = newTeamName.trim();
    if (!name) return;
    setCreatingTeam(true);
    const payload = { name, description: newTeamDescription.trim() || null };
    const result =
      mode === 'admin' && tenantId
        ? await createAdminTenantChatwootTeam(accessToken, tenantId, payload)
        : await createChatwootTeam(accessToken, payload);
    setCreatingTeam(false);
    if (!result.ok) {
      onNotify('error', result.detail);
      return;
    }
    setTeams((curr) => [...curr, result.data]);
    setNewTeamName('');
    setNewTeamDescription('');
    onNotify('success', `Team "${result.data.name}" creado.`);
  };

  const startEditTeam = (team: ChatwootTeamSummary) => {
    setEditingTeamId(team.id);
    setEditingTeamName(team.name);
  };

  const handleSaveTeam = async (teamId: number) => {
    const name = editingTeamName.trim();
    if (!name) return;
    const key = `team-${teamId}`;
    setBusyKey(key);
    const result =
      mode === 'admin' && tenantId
        ? await updateAdminTenantChatwootTeam(accessToken, tenantId, teamId, { name })
        : await updateChatwootTeam(accessToken, teamId, { name });
    setBusyKey(null);
    if (!result.ok) {
      onNotify('error', result.detail);
      return;
    }
    setTeams((curr) => curr.map((t) => (t.id === teamId ? result.data : t)));
    setEditingTeamId(null);
    onNotify('success', 'Team renombrado.');
  };

  const handleDeleteTeam = async (team: ChatwootTeamSummary) => {
    if (!window.confirm(`¿Borrar el team "${team.name}"? Esta acción no se puede deshacer.`)) return;
    const key = `team-${team.id}`;
    setBusyKey(key);
    const result =
      mode === 'admin' && tenantId
        ? await deleteAdminTenantChatwootTeam(accessToken, tenantId, team.id)
        : await deleteChatwootTeam(accessToken, team.id);
    setBusyKey(null);
    if (!result.ok) {
      onNotify('error', result.detail);
      return;
    }
    setTeams((curr) => curr.filter((t) => t.id !== team.id));
    onNotify('success', `Team "${team.name}" borrado.`);
  };

  const handleInviteAgent = async () => {
    const name = newAgentName.trim();
    const email = newAgentEmail.trim();
    if (!name || !email) return;
    setInvitingAgent(true);
    const payload = { name, email, role: newAgentRole };
    const result =
      mode === 'admin' && tenantId
        ? await inviteAdminTenantChatwootAgent(accessToken, tenantId, payload)
        : await inviteChatwootAgent(accessToken, payload);
    setInvitingAgent(false);
    if (!result.ok) {
      onNotify('error', result.detail);
      return;
    }
    setAgents((curr) => [...curr, result.data]);
    setNewAgentName('');
    setNewAgentEmail('');
    setNewAgentRole('agent');
    onNotify('success', `Invitación enviada a ${result.data.email}.`);
  };

  const startEditAgent = (agent: ChatwootAgentSummary) => {
    setEditingAgentId(agent.id);
    setEditingAgentName(agent.name);
    setEditingAgentRole(agent.role === 'administrator' ? 'administrator' : 'agent');
  };

  const handleSaveAgent = async (agentId: number) => {
    const name = editingAgentName.trim();
    if (!name) return;
    const key = `agent-${agentId}`;
    setBusyKey(key);
    const result =
      mode === 'admin' && tenantId
        ? await updateAdminTenantChatwootAgent(accessToken, tenantId, agentId, { name, role: editingAgentRole })
        : await updateChatwootAgent(accessToken, agentId, { name, role: editingAgentRole });
    setBusyKey(null);
    if (!result.ok) {
      onNotify('error', result.detail);
      return;
    }
    setAgents((curr) => curr.map((a) => (a.id === agentId ? result.data : a)));
    setEditingAgentId(null);
    onNotify('success', 'Agente actualizado.');
  };

  const handleDeleteAgent = async (agent: ChatwootAgentSummary) => {
    if (!window.confirm(`¿Quitar a "${agent.name}" de esta Account de Chatwoot?`)) return;
    const key = `agent-${agent.id}`;
    setBusyKey(key);
    const result =
      mode === 'admin' && tenantId
        ? await deleteAdminTenantChatwootAgent(accessToken, tenantId, agent.id)
        : await deleteChatwootAgent(accessToken, agent.id);
    setBusyKey(null);
    if (!result.ok) {
      onNotify('error', result.detail);
      return;
    }
    setAgents((curr) => curr.filter((a) => a.id !== agent.id));
    onNotify('success', `"${agent.name}" fue quitado de la Account.`);
  };

  if (loading) {
    return <div className="py-3 text-center text-xs text-muted-foreground">Cargando recursos de Chatwoot...</div>;
  }

  return (
    <div>
      <h3 className="text-sm font-medium text-muted-foreground">Recursos de Chatwoot</h3>
      <div className="mt-2 grid gap-3 sm:grid-cols-3">
        <div className="space-y-2 rounded-lg border border-border p-3">
          <h4 className="text-xs font-semibold text-foreground">Inboxes ({inboxes.length})</h4>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {inboxes.length === 0 && <li>Sin inboxes.</li>}
            {inboxes.map((inbox) =>
              editingInboxId === inbox.id ? (
                <li key={inbox.id} className="flex items-center gap-1">
                  <input
                    className={FIELD_CLASS}
                    value={editingInboxName}
                    onChange={(e) => setEditingInboxName(e.target.value)}
                    aria-label={`Renombrar inbox ${inbox.name}`}
                    autoFocus
                  />
                  <Button type="button" size="icon" variant="outline" className={ICON_BTN_CLASS} onClick={() => handleSaveInbox(inbox.id)} disabled={busyKey === `inbox-${inbox.id}` || !editingInboxName.trim()} aria-label="Guardar">
                    {busyKey === `inbox-${inbox.id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                  </Button>
                  <Button type="button" size="icon" variant="ghost" className={ICON_BTN_CLASS} onClick={() => setEditingInboxId(null)} aria-label="Cancelar">
                    <X className="h-3 w-3" />
                  </Button>
                </li>
              ) : (
                <li key={inbox.id} className="flex items-center justify-between gap-1">
                  <span className="truncate" title={inbox.name}>{inbox.name}</span>
                  <Button type="button" size="icon" variant="ghost" className={ICON_BTN_CLASS} onClick={() => startEditInbox(inbox)} aria-label={`Renombrar ${inbox.name}`}>
                    <Pencil className="h-3 w-3" />
                  </Button>
                </li>
              )
            )}
          </ul>
          <div className="flex gap-1">
            <input
              className={FIELD_CLASS}
              placeholder="Nombre del inbox"
              value={newInboxName}
              onChange={(e) => setNewInboxName(e.target.value)}
              aria-label="Nombre del nuevo inbox"
            />
            <Button type="button" size="icon" variant="outline" className="h-9 w-9 shrink-0" onClick={handleCreateInbox} disabled={creatingInbox || !newInboxName.trim()} aria-label="Crear inbox">
              {creatingInbox ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground/70">Chatwoot no permite borrar inboxes por API; hazlo desde Chatwoot si lo necesitas.</p>
        </div>

        <div className="space-y-2 rounded-lg border border-border p-3">
          <h4 className="text-xs font-semibold text-foreground">Teams ({teams.length})</h4>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {teams.length === 0 && <li>Sin teams.</li>}
            {teams.map((team) =>
              editingTeamId === team.id ? (
                <li key={team.id} className="flex items-center gap-1">
                  <input
                    className={FIELD_CLASS}
                    value={editingTeamName}
                    onChange={(e) => setEditingTeamName(e.target.value)}
                    aria-label={`Renombrar team ${team.name}`}
                    autoFocus
                  />
                  <Button type="button" size="icon" variant="outline" className={ICON_BTN_CLASS} onClick={() => handleSaveTeam(team.id)} disabled={busyKey === `team-${team.id}` || !editingTeamName.trim()} aria-label="Guardar">
                    {busyKey === `team-${team.id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                  </Button>
                  <Button type="button" size="icon" variant="ghost" className={ICON_BTN_CLASS} onClick={() => setEditingTeamId(null)} aria-label="Cancelar">
                    <X className="h-3 w-3" />
                  </Button>
                </li>
              ) : (
                <li key={team.id} className="flex items-center justify-between gap-1">
                  <span className="truncate" title={team.name}>{team.name}</span>
                  <span className="flex shrink-0 items-center gap-0.5">
                    <Button type="button" size="icon" variant="ghost" className={ICON_BTN_CLASS} onClick={() => startEditTeam(team)} aria-label={`Renombrar ${team.name}`}>
                      <Pencil className="h-3 w-3" />
                    </Button>
                    <Button type="button" size="icon" variant="ghost" className={`${ICON_BTN_CLASS} text-destructive hover:text-destructive`} onClick={() => handleDeleteTeam(team)} disabled={busyKey === `team-${team.id}`} aria-label={`Borrar ${team.name}`}>
                      {busyKey === `team-${team.id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                    </Button>
                  </span>
                </li>
              )
            )}
          </ul>
          <div className="space-y-1">
            <input
              className={FIELD_CLASS}
              placeholder="Nombre del team"
              value={newTeamName}
              onChange={(e) => setNewTeamName(e.target.value)}
              aria-label="Nombre del nuevo team"
            />
            <div className="flex gap-1">
              <input
                className={FIELD_CLASS}
                placeholder="Descripción (opcional)"
                value={newTeamDescription}
                onChange={(e) => setNewTeamDescription(e.target.value)}
                aria-label="Descripción del nuevo team"
              />
              <Button type="button" size="icon" variant="outline" className="h-9 w-9 shrink-0" onClick={handleCreateTeam} disabled={creatingTeam || !newTeamName.trim()} aria-label="Crear team">
                {creatingTeam ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              </Button>
            </div>
          </div>
        </div>

        <div className="space-y-2 rounded-lg border border-border p-3">
          <h4 className="text-xs font-semibold text-foreground">Agentes ({agents.length})</h4>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {agents.length === 0 && <li>Sin agentes.</li>}
            {agents.map((agent) =>
              editingAgentId === agent.id ? (
                <li key={agent.id} className="space-y-1 rounded-md border border-border/60 p-1.5">
                  <input
                    className={FIELD_CLASS}
                    value={editingAgentName}
                    onChange={(e) => setEditingAgentName(e.target.value)}
                    aria-label={`Renombrar agente ${agent.name}`}
                    autoFocus
                  />
                  <div className="flex gap-1">
                    <select
                      className={FIELD_CLASS}
                      value={editingAgentRole}
                      onChange={(e) => setEditingAgentRole(e.target.value as 'agent' | 'administrator')}
                      aria-label="Rol del agente"
                    >
                      <option value="agent">Agente</option>
                      <option value="administrator">Administrador</option>
                    </select>
                    <Button type="button" size="icon" variant="outline" className={ICON_BTN_CLASS} onClick={() => handleSaveAgent(agent.id)} disabled={busyKey === `agent-${agent.id}` || !editingAgentName.trim()} aria-label="Guardar">
                      {busyKey === `agent-${agent.id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                    </Button>
                    <Button type="button" size="icon" variant="ghost" className={ICON_BTN_CLASS} onClick={() => setEditingAgentId(null)} aria-label="Cancelar">
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </li>
              ) : (
                <li key={agent.id} className="flex items-center justify-between gap-1">
                  <span className="truncate" title={agent.email}>
                    {agent.name}
                    {!agent.confirmed && <span className="text-amber-600 dark:text-amber-400"> (pendiente)</span>}
                  </span>
                  <span className="flex shrink-0 items-center gap-0.5">
                    <Button type="button" size="icon" variant="ghost" className={ICON_BTN_CLASS} onClick={() => startEditAgent(agent)} aria-label={`Editar ${agent.name}`}>
                      <Pencil className="h-3 w-3" />
                    </Button>
                    <Button type="button" size="icon" variant="ghost" className={`${ICON_BTN_CLASS} text-destructive hover:text-destructive`} onClick={() => handleDeleteAgent(agent)} disabled={busyKey === `agent-${agent.id}`} aria-label={`Quitar ${agent.name}`}>
                      {busyKey === `agent-${agent.id}` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                    </Button>
                  </span>
                </li>
              )
            )}
          </ul>
          <div className="space-y-1">
            <input
              className={FIELD_CLASS}
              placeholder="Nombre"
              value={newAgentName}
              onChange={(e) => setNewAgentName(e.target.value)}
              aria-label="Nombre del nuevo agente"
            />
            <input
              className={FIELD_CLASS}
              type="email"
              placeholder="Email"
              value={newAgentEmail}
              onChange={(e) => setNewAgentEmail(e.target.value)}
              aria-label="Email del nuevo agente"
            />
            <div className="flex gap-1">
              <select
                className={FIELD_CLASS}
                value={newAgentRole}
                onChange={(e) => setNewAgentRole(e.target.value as 'agent' | 'administrator')}
                aria-label="Rol del nuevo agente"
              >
                <option value="agent">Agente</option>
                <option value="administrator">Administrador</option>
              </select>
              <Button
                type="button"
                size="icon"
                variant="outline"
                className="h-9 w-9 shrink-0"
                onClick={handleInviteAgent}
                disabled={invitingAgent || !newAgentName.trim() || !newAgentEmail.trim()}
                aria-label="Invitar agente"
              >
                {invitingAgent ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
