import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getTranslations } from 'next-intl/server';

import { PublicVoiceExperience } from '@/components/public/voice/PublicVoiceExperience';
import { fetchPublicVoiceExperience } from '@/lib/api/public-voice-experiences';

export const dynamic = 'force-dynamic';

interface PageProps {
  params: Promise<{ locale: string; slug: string }>;
}

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('publicVoiceExperience.metadata');
  return {
    title: t('title'),
    description: t('description'),
    robots: { index: false, follow: false },
  };
}

export default async function PublicVoiceExperiencePage({ params }: PageProps) {
  const { locale, slug } = await params;
  const [result, t] = await Promise.all([
    fetchPublicVoiceExperience(slug),
    getTranslations('publicVoiceExperience'),
  ]);

  if (!result.ok) notFound();

  return (
    <PublicVoiceExperience
      experience={result.data}
      locale={locale}
      messages={{
        eyebrow: t('eyebrow'),
        version: t('version'),
        required: t('required'),
        selectPlaceholder: t('selectPlaceholder'),
        privacy: t('privacy'),
        emptyFields: t('emptyFields'),
        noticeTitle: t('noticeTitle'),
        noticeDescription: t('noticeDescription'),
        logoAlt: t('logoAlt'),
        loading: t('loading'),
        successTitle: t('successTitle'),
        verificationUnavailable: t('verificationUnavailable'),
        microphoneHelp: t('microphoneHelp'),
        callLoading: t('callLoading'),
        callConnected: t('callConnected'),
        callDuration: t('callDuration'),
        voiceActivity: t('voiceActivity'),
        endCall: t('endCall'),
        callEnded: t('callEnded'),
        callbackLoading: t('callbackLoading'),
        callbackAccepted: t('callbackAccepted'),
        errors: {
          required: t('errors.required'),
          unknown_field: t('errors.unknown_field'),
          invalid_type: t('errors.invalid_type'),
          too_long: t('errors.too_long'),
          too_short: t('errors.too_short'),
          invalid_option: t('errors.invalid_option'),
          invalid_format: t('errors.invalid_format'),
          consent_required: t('errors.consent_required'),
          experience_version_changed: t('errors.experience_version_changed'),
          validation_error: t('errors.validation_error'),
          verification_failed: t('errors.verification_failed'),
          rate_limited: t('errors.rate_limited'),
          internal_error: t('errors.internal_error'),
          microphone_unavailable: t('errors.microphone_unavailable'),
          experience_unavailable: t('errors.experience_unavailable'),
          call_already_started: t('errors.call_already_started'),
          call_state_conflict: t('errors.call_state_conflict'),
          context_session_unavailable: t('errors.context_session_unavailable'),
          context_session_expired: t('errors.context_session_expired'),
          call_unavailable: t('errors.call_unavailable'),
          call_provider_unavailable: t('errors.call_provider_unavailable'),
          phone_unavailable: t('errors.phone_unavailable'),
          destination_not_allowed: t('errors.destination_not_allowed'),
          call_capacity_reached: t('errors.call_capacity_reached'),
        },
      }}
    />
  );
}
