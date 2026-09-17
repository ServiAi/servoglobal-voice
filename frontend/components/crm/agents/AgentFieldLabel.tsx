import { FieldHelp } from '@/components/crm/shared/FieldHelp';

export function AgentFieldLabel({ label, help, required = false, align = 'left', showLabel = true }: {
  label: string;
  help: string;
  required?: boolean;
  align?: 'left' | 'right';
  showLabel?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
      {showLabel ? <span>{label}</span> : null}
      <FieldHelp label={label} required={required} align={align}>{help}</FieldHelp>
    </span>
  );
}
