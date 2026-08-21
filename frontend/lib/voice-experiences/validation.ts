import { isSafeHttpsUrl } from './url-safety';
import type {
  VoiceContextFieldRequest,
  VoiceExperienceWriteRequest,
} from '@/types/voice-experiences';

export type ValidationCode = 'required' | 'invalid' | 'tooLong' | 'duplicate';
export type ValidationErrors = Record<string, ValidationCode>;

const LOCALE_PATTERN = /^[a-z]{2}(?:-[A-Z]{2})?$/;
const COLOR_PATTERN = /^#[0-9A-Fa-f]{6}$/;
const FIELD_KEY_PATTERN = /^[a-z][a-z0-9_]*$/;

export function createVoiceExperienceDefaults(locale: string): VoiceExperienceWriteRequest {
  const english = locale === 'en';
  return {
    agent_config_id: '',
    context_schema_id: '',
    name: '',
    default_locale: english ? 'en' : 'es',
    content: {
      title: english ? 'Talk with our advisor' : 'Habla con nuestro asesor',
      description: english
        ? 'Complete your details to get started.'
        : 'Completa tus datos para comenzar.',
      submit_label: english ? 'Continue' : 'Continuar',
      call_label: english ? 'Start call' : 'Iniciar llamada',
      success_message: english
        ? 'Your details were registered.'
        : 'Tus datos fueron registrados.',
    },
    theme: { logo_url: null, primary_color: null, layout: 'centered' },
    consent: {
      required: true,
      label: english
        ? 'I accept the processing of my personal data.'
        : 'Acepto el tratamiento de mis datos personales.',
      privacy_url: null,
    },
    call_settings: {
      auto_start: false,
      show_microphone_help: true,
      language: english ? 'en' : 'es',
      mode: 'webrtc',
      phone_field_key: null,
      default_country: 'CO',
    },
  };
}

function requireText(
  errors: ValidationErrors,
  path: string,
  value: string | null | undefined,
  maxLength: number
) {
  if (!value?.trim()) errors[path] = 'required';
  else if (value.length > maxLength) errors[path] = 'tooLong';
}

export function validateVoiceExperience(form: VoiceExperienceWriteRequest): ValidationErrors {
  const errors: ValidationErrors = {};
  requireText(errors, 'agent_config_id', form.agent_config_id, 36);
  requireText(errors, 'context_schema_id', form.context_schema_id, 36);
  requireText(errors, 'name', form.name, 160);
  requireText(errors, 'content.title', form.content.title, 160);
  requireText(errors, 'content.description', form.content.description, 2000);
  requireText(errors, 'content.submit_label', form.content.submit_label, 80);
  requireText(errors, 'content.call_label', form.content.call_label, 80);
  requireText(errors, 'content.success_message', form.content.success_message, 1000);
  if (!LOCALE_PATTERN.test(form.default_locale)) errors.default_locale = 'invalid';
  if (!LOCALE_PATTERN.test(form.call_settings.language)) errors['call_settings.language'] = 'invalid';
  if (form.call_settings.mode === 'callback' && !form.call_settings.phone_field_key) {
    errors['call_settings.phone_field_key'] = 'required';
  }
  if (form.theme.primary_color && !COLOR_PATTERN.test(form.theme.primary_color)) {
    errors['theme.primary_color'] = 'invalid';
  }
  if (form.theme.logo_url && !isSafeHttpsUrl(form.theme.logo_url)) {
    errors['theme.logo_url'] = 'invalid';
  }
  if (form.consent.privacy_url && !isSafeHttpsUrl(form.consent.privacy_url)) {
    errors['consent.privacy_url'] = 'invalid';
  }
  if (form.consent.required) {
    requireText(errors, 'consent.label', form.consent.label, 1000);
  }
  return errors;
}

export function validateContextField(field: VoiceContextFieldRequest): ValidationErrors {
  const errors: ValidationErrors = {};
  if (!FIELD_KEY_PATTERN.test(field.key)) errors.key = 'invalid';
  requireText(errors, 'label', field.label, 160);
  if (field.description && field.description.length > 1000) errors.description = 'tooLong';
  if (field.field_type === 'select') {
    if (field.options_json.length === 0) errors.options_json = 'required';
    const values = field.options_json.map((option) => option.value);
    if (new Set(values).size !== values.length) errors.options_json = 'duplicate';
  }
  return errors;
}
