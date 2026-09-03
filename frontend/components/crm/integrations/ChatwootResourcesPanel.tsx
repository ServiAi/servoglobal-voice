'use client';

import { useEffect, useState } from 'react';
import { Loader2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ChatwootAgentSummary, ChatwootInboxSummary, ChatwootTeamSummary } from '@/types/crm';
import {
  fetchChatwootInboxes,
  fetchAdminTenantChatwootInboxes,
  createChatwootInbox,
  createAdminTenantChatwootInbox,
  fetchChatwootTeams,
  fetchAdminTenantChatwootTeams,
  createChatwootTeam,
  createAdminTenantChatwootTeam,
  fetchChatwootAgents,
  fetchAdminTenantChatwootAgents,
  inviteChatwootAgent,
  inviteAdminTenantChatwootAgent,
} from '@/lib/api/crm';

type Props = {
  accessToken: string;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onNotify: (type: 'success' | 'error', text: string) => void;
};

const FIELD_CLASS = 'min-h-9 w-full min-w-0 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';

export function ChatwootResourcesPanel({ accessToken, mode = 'tenant', tenantId, onNotify }: Props) {
  const [inboxes, setInboxes] = useState<ChatwootInboxSummary[]>([]);
  const [teams, setTeams] = useState<ChatwootTeamSummary[]>([]);
  const [agents, setAgents] = useState<ChatwootAgentSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const [newInboxName, setNewInboxName] = useState('');
  const [creatingInbox, setCreatingInbox] = useState(false);

  const [newTeamName, setNewTeamName] = useState('');
  const [newTeamDescription, setNewTeamDescription] = useState('');
  const [creatingTeam, setCreatingTeam] = useState(false);

  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentEmail, setNewAgentEmail] = useState('');
  const [newAgentRole, setNewAgentRole] = useState<'agent' | 'administrator'>('agent');
  const [invitingAgent, setInvitingAgent] = useState(false);

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
      if (inboxesRes.ok) setInboxes(inboxesRes.data);
      if (teamsRes.ok) setTeams(teamsRes.data);
      if (agentsRes.ok) setAgents(agentsRes.data);
    }
    load();
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

  if (loading) {
    return <div className="py-3 text-center text-xs text-muted-foreground">Cargando recursos de Chatwoot...</div>;
  }

  return (
    <div>
      <h3 className="text-sm font-medium text-muted-foreground">Recursos de Chatwoot</h3>
      <div className="mt-2 grid gap-3 sm:grid-cols-3">
        <div className="space-y-2 rounded-lg border border-border p-3">
          <h4 className="text-xs font-semibold text-foreground">Inboxes</h4>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {inboxes.length === 0 && <li>Sin inboxes.</li>}
            {inboxes.map((inbox) => (
              <li key={inbox.id} className="truncate" title={inbox.name}>{inbox.name}</li>
            ))}
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
        </div>

        <div className="space-y-2 rounded-lg border border-border p-3">
          <h4 className="text-xs font-semibold text-foreground">Teams</h4>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {teams.length === 0 && <li>Sin teams.</li>}
            {teams.map((team) => (
              <li key={team.id} className="truncate" title={team.name}>{team.name}</li>
            ))}
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
          <h4 className="text-xs font-semibold text-foreground">Agentes</h4>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {agents.length === 0 && <li>Sin agentes.</li>}
            {agents.map((agent) => (
              <li key={agent.id} className="truncate" title={agent.email}>
                {agent.name}
                {!agent.confirmed && <span className="text-amber-600 dark:text-amber-400"> (pendiente)</span>}
              </li>
            ))}
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
