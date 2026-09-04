import { redirect } from 'next/navigation';

type Props = {
  params: Promise<{ locale: string; experienceId: string }>;
};

export default async function LegacyVoiceExperienceEditorRedirect({ params }: Props) {
  const { locale, experienceId } = await params;
  redirect(`/${locale}/voice-ai/experiences/${experienceId}`);
}
