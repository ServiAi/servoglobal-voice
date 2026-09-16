export type VoicePreviewMediaType = 'audio/wav' | 'audio/mpeg';

export function parseVoicePreviewMediaType(contentType: string | null): VoicePreviewMediaType | null {
  const mediaType = contentType?.split(';', 1)[0].trim().toLowerCase();
  return mediaType === 'audio/wav' || mediaType === 'audio/mpeg' ? mediaType : null;
}
