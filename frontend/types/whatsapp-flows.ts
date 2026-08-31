export type WhatsAppFlowCategory =
  | 'SIGN_UP'
  | 'SIGN_IN'
  | 'APPOINTMENT_BOOKING'
  | 'LEAD_GENERATION'
  | 'CONTACT_US'
  | 'CUSTOMER_SUPPORT'
  | 'SURVEY'
  | 'OTHER';

export type WhatsAppFlowComponentType =
  | 'heading'
  | 'body'
  | 'text_input'
  | 'email_input'
  | 'phone_input'
  | 'number_input'
  | 'text_area'
  | 'dropdown'
  | 'radio'
  | 'checkbox'
  | 'date'
  | 'footer';

export type WhatsAppFlowOption = { id: string; title: string; context_value?: string | null };
export type WhatsAppFlowNavigationAction = {
  type: 'navigate' | 'complete';
  target_screen_id?: string | null;
};
export type WhatsAppFlowContextBinding = {
  context_field_key: string;
  prefill_supported_later?: boolean;
};
export type WhatsAppFlowComponent = {
  id: string;
  type: WhatsAppFlowComponentType;
  label?: string | null;
  text?: string | null;
  placeholder?: string | null;
  required?: boolean;
  options?: WhatsAppFlowOption[];
  action?: WhatsAppFlowNavigationAction | null;
  binding?: WhatsAppFlowContextBinding | null;
};
export type WhatsAppFlowScreen = {
  id: string;
  title: string;
  terminal: boolean;
  components: WhatsAppFlowComponent[];
};
export type WhatsAppFlowBuilder = { version: 1; screens: WhatsAppFlowScreen[] };

export type WhatsAppFlowValidationError = {
  error?: string | null;
  error_type?: string | null;
  message?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  column_start?: number | null;
  column_end?: number | null;
};

export type WhatsAppFlow = {
  id: string;
  flow_key: string;
  version: number;
  parent_flow_id?: string | null;
  name: string;
  categories: WhatsAppFlowCategory[];
  source_mode: 'visual' | 'context_schema';
  context_schema_id?: string | null;
  context_schema_snapshot?: {
    fields?: Array<{ key: string; label: string; field_type: string }>;
  } | null;
  status: 'draft' | 'synced' | 'published' | 'deprecated' | 'error';
  meta_status?: string | null;
  provider_flow_id?: string | null;
  builder_schema_version: number;
  builder: WhatsAppFlowBuilder;
  compiled_flow_json?: Record<string, unknown> | null;
  compiled_hash?: string | null;
  validation_errors: WhatsAppFlowValidationError[];
  last_synced_at?: string | null;
  published_at?: string | null;
  deprecated_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type WhatsAppFlowCreateRequest = {
  name: string;
  flow_key: string;
  categories: WhatsAppFlowCategory[];
  source_mode: 'visual' | 'context_schema';
  context_schema_id?: string | null;
  builder?: WhatsAppFlowBuilder | null;
};
export type WhatsAppFlowUpdateRequest = {
  name?: string;
  categories?: WhatsAppFlowCategory[];
  builder?: WhatsAppFlowBuilder;
};
export type WhatsAppFlowCompileResponse = {
  compiled_flow_json: Record<string, unknown>;
  compiled_hash: string;
};

export type WhatsAppFlowContextSchemaOption = {
  id: string;
  name: string;
  schema_key: string;
  version: number;
  status: string;
  agent_name: string;
};
