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
  capabilities: {
    submissions: false;
    calls: false;
  };
}
