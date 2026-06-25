export function canEditLead(role?: string) {
  return role === 'platform_admin' || role === 'tenant_admin';
}

export function canChangeTerminalStage(role?: string) {
  return role === 'platform_admin' || role === 'tenant_admin';
}

export function canCreateNote(role?: string) {
  return role === 'platform_admin' || role === 'tenant_admin' || role === 'tenant_analyst';
}

export function canCreateTask(role?: string) {
  return role === 'platform_admin' || role === 'tenant_admin' || role === 'tenant_analyst';
}

export function canUpdateTask(role?: string) {
  return role === 'platform_admin' || role === 'tenant_admin' || role === 'tenant_analyst';
}

export function canDeleteTask(role?: string) {
  return role === 'platform_admin' || role === 'tenant_admin';
}

export function canUseOutboundActions(role?: string) {
  return role === 'platform_admin' || role === 'tenant_admin' || role === 'tenant_analyst';
}

export function canViewFullDetail(role?: string) {
  return true; // All roles can view detail
}
