export type CustomToolAuthType = 'none' | 'bearer' | 'api_key' | 'basic';
export type CustomToolMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
export type CustomToolStatus = 'active' | 'disabled';
export type CustomToolGateState = 'ok' | 'feature_disabled' | 'access_denied' | 'error';

export type CustomToolCredentialMasked = {
  auth_type: CustomToolAuthType;
  configured: boolean;
  api_key_header_name: string | null;
  masked_fields: Record<string, string>;
};

export type CustomToolResponse = {
  id: string;
  tenant_id: string;
  key: string;
  name: string;
  description: string;
  status: CustomToolStatus;
  method: CustomToolMethod;
  base_url: string;
  path_template: string;
  timeout_ms: number;
  headers: Record<string, string>;
  path_mapping: Record<string, string>;
  query_mapping: Record<string, string>;
  body_mapping: Record<string, string>;
  input_schema: Record<string, unknown>;
  response_mapping: Record<string, string>;
  credential: CustomToolCredentialMasked;
  created_at: string;
  updated_at: string;
};

export type CustomToolCreateRequest = {
  key: string;
  name: string;
  description: string;
  method: CustomToolMethod;
  base_url: string;
  path_template?: string;
  timeout_ms?: number;
  headers?: Record<string, string>;
  path_mapping?: Record<string, string>;
  query_mapping?: Record<string, string>;
  body_mapping?: Record<string, string>;
  input_schema?: Record<string, unknown>;
  response_mapping?: Record<string, string>;
  auth_type?: CustomToolAuthType;
  api_key_header_name?: string | null;
  secrets?: Record<string, string> | null;
};

export type CustomToolUpdateRequest = Partial<Omit<CustomToolCreateRequest, 'key'>>;

export type CustomToolTestRequest = {
  arguments: Record<string, unknown>;
};

export type CustomToolTestResponse = {
  success: boolean;
  status_code: number | null;
  latency_ms: number | null;
  mapped_result: Record<string, unknown> | null;
  error_code: string | null;
};
