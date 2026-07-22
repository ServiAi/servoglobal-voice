export const CRM_STAGES = [
  ['new', 'Nuevo'], ['contacted', 'Contactado'], ['connected', 'Conectado'],
  ['qualified', 'Calificado'], ['scheduled', 'Agendado'], ['voicemail', 'Buzón de voz'],
  ['follow_up', 'En seguimiento'], ['not_interested', 'No interesado'], ['won', 'Ganado'], ['lost', 'Perdido'],
].map(([key, label]) => ({ key, label }));

export const CRM_STATUSES = [
  ['open', 'Abierto'], ['won', 'Ganado'], ['lost', 'Perdido'],
  ['unqualified', 'Descalificado'], ['paused', 'Pausado'],
].map(([key, label]) => ({ key, label }));

export const getStageLabel = (key: string, fallback?: string) => CRM_STAGES.find((item) => item.key === key)?.label ?? fallback ?? key;
export const getStatusLabel = (key: string) => CRM_STATUSES.find((item) => item.key === key)?.label ?? key;
