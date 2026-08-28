export type EmbedMode = 'inline' | 'floating' | 'modal';
export type EmbedCodeFormat = 'html' | 'react' | 'iframe';
export type FloatingPosition = 'bottom-right' | 'bottom-left';

export interface BuildEmbedSnippetInput {
  mode: EmbedMode;
  format: EmbedCodeFormat;
  embedUrl: string;
  sdkUrl: string;
  floatingText?: string;
  floatingPosition?: FloatingPosition;
  modalSelector?: string;
}

export function buildEmbedSnippet(input: BuildEmbedSnippetInput): string {
  if (input.format === 'iframe') {
    return [
      '<iframe',
      `  src="${input.embedUrl}"`,
      '  style="width:100%;border:0;"',
      '  allow="microphone; autoplay"',
      '  title="Voice assistant"',
      '  height="640"',
      '></iframe>',
    ].join('\n');
  }

  if (input.format === 'react') {
    const mountCall =
      input.mode === 'inline'
        ? `window.VoiceEmbed.mountInline('#voice-embed-root', { src: '${input.embedUrl}' })`
        : input.mode === 'floating'
          ? `window.VoiceEmbed.mountFloating({ src: '${input.embedUrl}', text: '${input.floatingText ?? ''}', position: '${input.floatingPosition ?? 'bottom-right'}' })`
          : `window.VoiceEmbed.mountModal({ src: '${input.embedUrl}', trigger: '${input.modalSelector ?? '#reservar-demo'}' })`;
    const rootElement = input.mode === 'inline' ? "\n      <div id=\"voice-embed-root\" />" : '';
    return [
      "useEffect(() => {",
      "  const script = document.createElement('script');",
      `  script.src = '${input.sdkUrl}';`,
      '  script.async = true;',
      `  script.onload = () => ${mountCall};`,
      '  document.body.appendChild(script);',
      '  return () => script.remove();',
      '}, []);',
      rootElement ? `\nreturn (<>${rootElement}\n    </>);` : '',
    ]
      .filter(Boolean)
      .join('\n');
  }

  // format === 'html'
  if (input.mode === 'inline') {
    return [
      `<div data-voice-embed="inline" data-voice-embed-src="${input.embedUrl}"></div>`,
      `<script src="${input.sdkUrl}" async></script>`,
    ].join('\n');
  }

  if (input.mode === 'floating') {
    return [
      `<script src="${input.sdkUrl}" async`,
      '  data-voice-embed="floating"',
      `  data-voice-embed-src="${input.embedUrl}"`,
      `  data-voice-embed-text="${input.floatingText ?? ''}"`,
      `  data-voice-embed-position="${input.floatingPosition ?? 'bottom-right'}"></script>`,
    ].join('\n');
  }

  return [
    `<script src="${input.sdkUrl}" async`,
    '  data-voice-embed="modal"',
    `  data-voice-embed-src="${input.embedUrl}"`,
    `  data-voice-embed-trigger="${input.modalSelector ?? '#reservar-demo'}"></script>`,
  ].join('\n');
}
