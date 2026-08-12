export type PublicVoiceFieldType =
  | 'text'
  | 'textarea'
  | 'email'
  | 'phone'
  | 'integer'
  | 'select'
  | 'checkbox'
  | 'date';

export interface PublicVoiceFieldOption {
  value: string;
  label: string;
}

export interface PublicVoiceContextField {
  key: string;
  label: string;
  description: string | null;
  field_type: PublicVoiceFieldType;
  required: boolean;
  options: PublicVoiceFieldOption[];
}

export interface PublicVoiceExperience {
  slug: string;
  locale: string;
  version: number;
  content: {
    title: string;
    description: string;
    submit_label: string;
    call_label: string;
    success_message: string;
  };
  theme: {
    logo_url: string | null;
    primary_color: string | null;
    layout: 'centered' | 'split' | 'card';
  };
  consent: {
    required: boolean;
    label: string | null;
    privacy_url: string | null;
  };
  fields: PublicVoiceContextField[];
  call_settings: {
    auto_start: boolean;
    show_microphone_help: boolean;
    language: string;
  };
  capabilities: {
    submissions: true;
    calls: true;
  };
}

export type PublicSubmissionFieldErrorCode =
  | 'required'
  | 'unknown_field'
  | 'invalid_type'
  | 'too_long'
  | 'too_short'
  | 'invalid_option'
  | 'invalid_format'
  | 'consent_required';

export type PublicSubmissionErrorCode =
  | 'experience_version_changed'
  | 'validation_error'
  | 'verification_failed'
  | 'rate_limited'
  | 'internal_error';

export interface PublicSubmissionResponse {
  status: 'accepted';
  context_token: string;
  expires_at: string;
  capabilities: { submissions: true; calls: false };
}

export interface PublicSubmissionFailure {
  code: PublicSubmissionErrorCode;
  fields: Array<{ key: string; code: PublicSubmissionFieldErrorCode }>;
}
