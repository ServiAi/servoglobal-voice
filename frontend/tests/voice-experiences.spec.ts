import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import enMessages from '../messages/en.json';
import esMessages from '../messages/es.json';
import { resolveVoiceExperienceGateState } from '../lib/permissions/voice-experiences';
import {
  isVoiceExperienceAgentLocked,
  isVoiceExperienceDirty,
} from '../lib/voice-experiences/change-detection';
import { getPreCallVisibleContextFields } from '../lib/voice-experiences/collection-modes';
import { canDeleteArchivedExperience } from '../lib/voice-experiences/deletion';
import {
  getVoiceExperienceErrorKey,
  getVoiceExperienceMessageKey,
} from '../lib/voice-experiences/error-messages';
import { isSafeHttpsUrl } from '../lib/voice-experiences/url-safety';
import { createVoiceExperienceDefaults } from '../lib/voice-experiences/validation';
import type { VoiceContextCollectionMode } from '../types/voice-experiences';

const PATH = '/es/crm/settings/voice-experiences';

async function requireAuthenticatedInventory(page: import('@playwright/test').Page) {
  await page.goto(PATH, { waitUntil: 'networkidle' });
  test.skip(
    (await page.getByRole('heading', { name: /Te damos la bienvenida/i }).count()) > 0,
    'La sesión Auth0 de Playwright está vencida.'
  );
}

test.describe('protecciones puras de Voice Experiences', () => {
  test('acepta únicamente URLs HTTPS explícitas', () => {
    expect(isSafeHttpsUrl('https://cdn.example.test/logo.svg')).toBe(true);
    expect(isSafeHttpsUrl('http://cdn.example.test/logo.svg')).toBe(false);
    expect(isSafeHttpsUrl('javascript:alert(1)')).toBe(false);
    expect(isSafeHttpsUrl('not-a-url')).toBe(false);
  });

  test('detecta cambios del borrador sin mutar su configuración', () => {
    const baseline = createVoiceExperienceDefaults('es');
    expect(isVoiceExperienceDirty(baseline, baseline)).toBe(false);
    expect(isVoiceExperienceDirty(baseline, { ...baseline, name: 'Recepción' })).toBe(true);
  });

  test('mantiene traducidos todos los estados, incluido unpublished', () => {
    expect(esMessages.crm.voiceExperiences.list.status.unpublished).toBe('Despublicada');
    expect(enMessages.crm.voiceExperiences.list.status.unpublished).toBe('Unpublished');
  });

  test('explica el paso siguiente cuando una experiencia está publicada', () => {
    expect(esMessages.crm.voiceExperiences.list.status.published).toBe('Publicada');
    expect(enMessages.crm.voiceExperiences.list.status.published).toBe('Published');
    expect(esMessages.crm.voiceExperiences.actions.publish).toBe('Publicar');
    expect(esMessages.crm.voiceExperiences.actions.unpublish).toBe('Despublicar');
    expect(enMessages.crm.voiceExperiences.actions.publish).toBe('Publish');
    expect(enMessages.crm.voiceExperiences.actions.unpublish).toBe('Unpublish');
    expect(esMessages.crm.voiceExperiences.list.privateNotice).toMatch(/página pública/i);
    expect(enMessages.crm.voiceExperiences.list.privateNotice).toMatch(/public page/i);
    expect(esMessages.crm.voiceExperiences.list.openPublic).toBeTruthy();
    expect(esMessages.crm.voiceExperiences.list.copyLink).toBeTruthy();
  });

  test('el helper de collection modes decide qué campos aparecen antes de la llamada', () => {
    const modes: VoiceContextCollectionMode[] = [
      'internal_only',
      'ask_if_missing',
      'collect_during_call',
      'trust_prefill',
      'prefill_and_confirm',
    ];
    const fields = modes.map((mode, index) => ({
      collection_mode: mode,
      // Deliberately unsorted so we also assert ordering by position.
      position: modes.length - index,
    }));
    const visible = getPreCallVisibleContextFields(fields);
    expect(visible.map((field) => field.collection_mode)).toEqual([
      'prefill_and_confirm',
      'trust_prefill',
      'ask_if_missing',
    ]);
    // internal_only and collect_during_call never render in the pre-call form.
    expect(visible.some((field) => field.collection_mode === 'internal_only')).toBe(false);
    expect(visible.some((field) => field.collection_mode === 'collect_during_call')).toBe(false);
  });

  test('distingue integración deshabilitada de integración sin agentes', () => {
    const base = { canRead: true, experiencesStatus: null, agentCount: 0 };
    expect(resolveVoiceExperienceGateState({ ...base, agentsStatus: 404 })).toBe(
      'integration_disabled'
    );
    expect(resolveVoiceExperienceGateState({ ...base, agentsStatus: null })).toBe('no_agents');
  });

  test('localiza los errores conocidos del backend y conserva fallback para desconocidos', () => {
    expect(getVoiceExperienceErrorKey('Voice experience is already published.')).toBe(
      'alreadyPublished'
    );
    expect(getVoiceExperienceErrorKey('Unknown backend detail.')).toBeUndefined();
    expect(esMessages.crm.voiceExperiences.errors.backend.alreadyPublished).toBe(
      'La experiencia ya está publicada.'
    );
  });

  test('localiza los nuevos conflictos de dominio (agente e historial)', () => {
    expect(
      getVoiceExperienceErrorKey(
        'Voice experience agent cannot change after publication history exists.'
      )
    ).toBe('agentChangeBlocked');
    expect(
      getVoiceExperienceErrorKey(
        'Voice experience with publication history cannot be deleted.'
      )
    ).toBe('deleteHistoryBlocked');
    expect(esMessages.crm.voiceExperiences.errors.backend.agentChangeBlocked).toBeTruthy();
    expect(esMessages.crm.voiceExperiences.errors.backend.deleteHistoryBlocked).toBeTruthy();
    expect(enMessages.crm.voiceExperiences.errors.backend.agentChangeBlocked).toBeTruthy();
    expect(enMessages.crm.voiceExperiences.errors.backend.deleteHistoryBlocked).toBeTruthy();
    expect(
      getVoiceExperienceErrorKey(
        'Voice context schema is referenced by publication history and cannot be deleted.'
      )
    ).toBe('schemaDeleteReferenced');
    expect(esMessages.crm.voiceExperiences.errors.backend.schemaDeleteReferenced).toBeTruthy();
    expect(enMessages.crm.voiceExperiences.errors.backend.schemaDeleteReferenced).toBeTruthy();
    expect(
      getVoiceExperienceErrorKey(
        'The current published voice experience version cannot be deleted.'
      )
    ).toBe('versionDeleteCurrent');
    expect(
      getVoiceExperienceErrorKey('The latest voice experience version cannot be deleted.')
    ).toBe('versionDeleteLatest');
    expect(
      getVoiceExperienceErrorKey('A referenced voice experience version cannot be deleted.')
    ).toBe('versionDeleteReferenced');
    expect(esMessages.crm.voiceExperiences.versions.confirmRestore.description).toBeTruthy();
    expect(esMessages.crm.voiceExperiences.versions.confirmDelete.description).toContain(
      'permanentemente'
    );
    expect(enMessages.crm.voiceExperiences.versions.confirmDelete.description).toContain(
      'permanently'
    );
  });

  test('explica el flujo editable y recuperable de los esquemas de contexto', () => {
    expect(esMessages.crm.voiceExperiences.contextSchemas.editAsNewVersion).toMatch(
      /nueva versión/i
    );
    expect(esMessages.crm.voiceExperiences.contextSchemas.openDraft).toMatch(/borrador/i);
    expect(esMessages.crm.voiceExperiences.contextSchemas.fields.readOnlyHint).toMatch(
      /borrador/i
    );
    expect(enMessages.crm.voiceExperiences.contextSchemas.editAsNewVersion).toBeTruthy();
    expect(enMessages.crm.voiceExperiences.contextSchemas.openDraft).toBeTruthy();
  });

  test('bloquea el agente cuando el historial existe o no pudo verificarse', () => {
    expect(isVoiceExperienceAgentLocked('edit', false, 1)).toBe(true);
    expect(isVoiceExperienceAgentLocked('edit', true, 0)).toBe(true);
    expect(isVoiceExperienceAgentLocked('edit', false, 0)).toBe(false);
    expect(isVoiceExperienceAgentLocked('create', true, 0)).toBe(false);
    expect(esMessages.crm.voiceExperiences.editor.agentLockedHistoryUnknown).toBe(
      'No pudimos verificar el historial de publicaciones. El agente permanece bloqueado hasta poder validarlo.'
    );
    expect(enMessages.crm.voiceExperiences.editor.agentLockedHistoryUnknown).toBe(
      'We could not verify the publication history. The agent remains locked until it can be validated.'
    );
  });

  test('nunca muestra un backend detail arbitrario al usuario', () => {
    // Known detail → specific backend key.
    expect(
      getVoiceExperienceMessageKey(409, 'Voice experience is already published.')
    ).toBe('errors.backend.alreadyPublished');
    // Unknown 409/422 → localized fallback, never the raw detail.
    expect(getVoiceExperienceMessageKey(409, 'Some raw internal detail')).toBe('errors.conflict');
    expect(getVoiceExperienceMessageKey(422, 'Another raw detail')).toBe('errors.validation');
    expect(getVoiceExperienceMessageKey(403, 'x')).toBe('errors.accessDenied');
    expect(getVoiceExperienceMessageKey(404, 'x')).toBe('errors.notFound');
    expect(getVoiceExperienceMessageKey(500, 'x')).toBe('errors.generic');
    // The returned keys must resolve to real translations in both locales.
    for (const messages of [esMessages, enMessages]) {
      for (const status of [400, 403, 404, 409, 422, 500]) {
        const key = getVoiceExperienceMessageKey(status, 'raw');
        const value = key
          .split('.')
          .reduce<Record<string, unknown> | string | undefined>(
            (node, part) =>
              node && typeof node === 'object'
                ? (node as Record<string, unknown>)[part] as Record<string, unknown> | string
                : undefined,
            messages.crm.voiceExperiences as unknown as Record<string, unknown>
          );
        expect(typeof value).toBe('string');
      }
    }
  });

  test('la eliminación solo se ofrece para experiencias archivadas', () => {
    expect(canDeleteArchivedExperience('archived')).toBe(true);
    expect(canDeleteArchivedExperience('draft')).toBe(false);
    expect(canDeleteArchivedExperience('unpublished')).toBe(false);
    expect(canDeleteArchivedExperience('published')).toBe(false);
  });

  test('advierte claramente que la eliminación es definitiva', () => {
    expect(esMessages.crm.voiceExperiences.confirm.delete.description).toContain('permanentemente');
    expect(enMessages.crm.voiceExperiences.confirm.delete.description).toContain('permanently');
    expect(esMessages.crm.voiceExperiences.confirm.delete.confirmLabel).toBeTruthy();
    expect(enMessages.crm.voiceExperiences.confirm.delete.confirmLabel).toBeTruthy();
  });
});

test.describe('administración privada de Voice Experiences', () => {
  test('muestra el inventario o un estado de acceso controlado sin exponer secretos', async ({ page }) => {
    await requireAuthenticatedInventory(page);

    await expect(
      page.getByRole('heading', { name: /Experiencias de voz/i })
        .or(page.getByRole('heading', { name: /Funcionalidad no habilitada|Integración de voz pendiente|Acceso restringido|No pudimos cargar/i }))
    ).toBeVisible();

    const visibleText = await page.locator('body').innerText();
    expect(visibleText).not.toMatch(/access_token|authorization|api[_ -]?key|provider_agent_id|joinUrl|webRTC/i);
  });

  test('no desborda en viewport móvil', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await requireAuthenticatedInventory(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test('el builder mantiene una vista previa local y accesible cuando se puede crear', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const createLink = page.getByRole('link', { name: /Nueva experiencia/i }).first();
    test.skip((await createLink.count()) === 0, 'El tenant o el rol no permite crear experiencias.');

    await createLink.click();
    await expect(page.getByRole('heading', { name: /Crear experiencia de voz/i })).toBeVisible();
    const preview = page.getByTestId('voice-experience-preview');
    await expect(preview).toBeVisible();
    await expect(page.getByText(/Vista no funcional/i)).toBeVisible();
    // On the default Form state no call/mic action is offered.
    await expect(page.getByRole('button', { name: /Unirse|Iniciar llamada|Permitir micrófono/i })).toHaveCount(0);

    // Microphone help belongs to "Antes de la llamada", never to the form.
    const micHelp = preview.getByText(/acceso al micrófono/i);
    await expect(micHelp).toHaveCount(0);

    // The three local states are reachable and stay non-functional.
    await preview.getByRole('tab', { name: /^Confirmación$/i }).click();
    await preview.getByRole('tab', { name: /^Antes de la llamada$/i }).click();
    // Either a simulated (disabled) call button or the auto-start note is shown.
    const callButton = preview.getByRole('button', { disabled: true }).last();
    await expect(callButton.or(page.getByText(/se iniciaría automáticamente/i))).toBeVisible();
    // Microphone help only appears in the before-call state.
    await expect(micHelp).toBeVisible();
    await preview.getByRole('tab', { name: /^Formulario$/i }).click();
    await expect(micHelp).toHaveCount(0);

    const accessibility = await new AxeBuilder({ page })
      .include('[data-testid="voice-experience-preview"]')
      .analyze();
    expect(accessibility.violations, JSON.stringify(accessibility.violations, null, 2)).toEqual([]);
  });

  test('las tarjetas del inventario no ofrecen publicar ni despublicar', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const cards = page.locator('article');
    test.skip((await cards.count()) === 0, 'No hay experiencias en el inventario.');
    await expect(
      cards.getByRole('button', { name: /Publicar|Despublicar/i })
    ).toHaveCount(0);
  });

  test('la publicación y despublicación viven en el editor', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const openEditor = page.getByRole('link', { name: /Abrir editor/i }).first();
    test.skip((await openEditor.count()) === 0, 'No hay una experiencia editable en el tenant QA.');
    await openEditor.click();
    await expect(
      page
        .getByRole('button', { name: /^Publicar$/i })
        .or(page.getByRole('button', { name: /^Despublicar$/i }))
    ).toBeVisible();
  });

  test('permite seleccionar una versión y cargar su vista previa histórica', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const openEditor = page.getByRole('link', { name: /Abrir editor/i }).first();
    test.skip((await openEditor.count()) === 0, 'No hay una experiencia editable en el tenant QA.');
    await openEditor.click();
    await page.getByRole('tab', { name: /^Versiones$/i }).click();
    const version = page.getByTestId(/^voice-version-/).first();
    test.skip((await version.count()) === 0, 'La experiencia no tiene historial publicado.');

    await version.click();
    await expect(version).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByText(/Vista previa histórica: versión/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Restaurar como borrador/i }).first()).toBeVisible();
  });

  test('una experiencia publicada ofrece abrir y copiar su enlace público', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const publishedCard = page
      .locator('article')
      .filter({ has: page.getByText('Publicada', { exact: true }) })
      .first();
    test.skip((await publishedCard.count()) === 0, 'No hay una experiencia publicada en el tenant QA.');

    const publicLink = publishedCard.getByRole('link', { name: /Abrir página pública/i });
    await expect(publicLink).toHaveAttribute('href', /\/es\/voice\/[A-Za-z0-9_-]+$/);
    await expect(publicLink).toHaveAttribute('target', '_blank');
    await expect(publishedCard.getByRole('button', { name: /Copiar enlace/i })).toBeVisible();
  });

  test('limpia el detalle de schema al cambiar de agente', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const openEditor = page.getByRole('link', { name: /Abrir editor/i }).first();
    test.skip((await openEditor.count()) === 0, 'No hay una experiencia editable en el tenant QA.');
    await openEditor.click();

    const agentContextTab = page.getByRole('tab', { name: /Agente y contexto/i });
    await agentContextTab.click();
    const agentSelect = page.getByLabel(/^Agente$/i);
    test.skip(await agentSelect.isDisabled(), 'El agente está bloqueado por historial publicado.');
    const options = await agentSelect.locator('option:not([value=""])').evaluateAll((items) =>
      items.map((item) => ({ value: (item as HTMLOptionElement).value }))
    );
    test.skip(options.length < 2, 'Se requieren dos agentes activos para esta regresión.');

    const schemaItems = page.getByRole('listitem');
    test.skip((await schemaItems.count()) === 0, 'El agente actual no tiene schemas.');
    await schemaItems.first().click();
    await expect(page.getByTestId('context-schema-detail')).toBeVisible();
    const currentAgent = await agentSelect.inputValue();
    await agentSelect.selectOption(options.find((option) => option.value !== currentAgent)!.value);
    await expect(page.getByTestId('context-schema-empty-detail')).toBeVisible();
  });

  test('mantiene la última selección cuando dos schemas responden fuera de orden', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const openEditor = page.getByRole('link', { name: /Abrir editor/i }).first();
    test.skip((await openEditor.count()) === 0, 'No hay experiencias para abrir el editor.');
    await openEditor.click();
    await page.getByRole('tab', { name: /Agente y contexto/i }).click();
    const schemas = page.getByRole('listitem');
    test.skip((await schemas.count()) < 2, 'Se requieren dos schemas para probar respuestas fuera de orden.');
    const lastName = (await schemas.nth(1).innerText()).split('\n')[0].trim();
    await schemas.first().click();
    await schemas.nth(1).click();
    await expect(page.getByTestId('context-schema-detail').getByRole('heading', { name: lastName })).toBeVisible();
  });

  test('permite abrir una versión concreta del esquema desde su historial', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const openEditor = page.getByRole('link', { name: /Abrir editor/i }).first();
    test.skip((await openEditor.count()) === 0, 'No hay experiencias para abrir el editor.');
    await openEditor.click();
    await page.getByRole('tab', { name: /Agente y contexto/i }).click();
    const schemaItems = page.getByRole('listitem');
    test.skip((await schemaItems.count()) === 0, 'El agente actual no tiene schemas.');
    await schemaItems.first().click();
    const schemaVersion = page
      .getByRole('button', { name: /^v\d+ · (Borrador|Activo|Archivado)$/i })
      .first();
    test.skip((await schemaVersion.count()) === 0, 'El esquema no tiene historial visible.');
    await schemaVersion.click();
    await expect(schemaVersion).toHaveAttribute('aria-pressed', 'true');
  });

  test('abre y selecciona el borrador existente sin intentar crear otro', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const openEditor = page.getByRole('link', { name: /Abrir editor/i }).first();
    test.skip((await openEditor.count()) === 0, 'No hay experiencias para abrir el editor.');
    await openEditor.click();
    await page.getByRole('tab', { name: /Agente y contexto/i }).click();
    const openDraft = page.getByRole('button', { name: /Abrir borrador editable/i }).first();
    test.skip((await openDraft.count()) === 0, 'No hay un borrador existente para esta regresión.');

    await openDraft.click();
    await expect(page.getByTestId('context-schema-detail').getByText('Borrador', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /Seleccionado/i })).toBeVisible();
    await expect(page.getByText(/La operación entra en conflicto/i)).toHaveCount(0);
  });

  test('asocia cada pestaña del editor con su tabpanel e indica secciones inválidas', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const openEditor = page.getByRole('link', { name: /Abrir editor/i }).first();
    test.skip((await openEditor.count()) === 0, 'No hay experiencias para abrir el editor.');
    await openEditor.click();
    const contentTab = page.getByRole('tab', { name: /^Contenido$/i });
    await expect(page.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', /voice-experience-tab-/);
    await contentTab.click();
    const title = page.getByLabel(/^Título$/i);
    test.skip(await title.isDisabled(), 'La experiencia es de solo lectura.');
    await title.fill('');
    await page.getByRole('tab', { name: /^Apariencia$/i }).click();
    await page.getByRole('button', { name: /^Guardar$/i }).click();
    await expect(contentTab).toHaveAttribute('data-invalid', 'true');
    await expect(page.getByRole('tabpanel')).toHaveAttribute(
      'aria-labelledby',
      'voice-experience-tab-appearance'
    );
  });

  test('cubre CRUD de campos con un seed desechable', async ({ page }) => {
    test.skip(
      process.env.VOICE_EXPERIENCE_E2E_MUTATIONS !== '1',
      'Requiere un schema draft desechable; habilitar sólo en el tenant QA sembrado.'
    );
    await requireAuthenticatedInventory(page);
    const createLink = page.getByRole('link', { name: /Nueva experiencia/i }).first();
    test.skip((await createLink.count()) === 0, 'El rol no permite crear schemas.');
    await createLink.click();
    const agentSelect = page.getByLabel(/^Agente$/i);
    const agentValue = await agentSelect.locator('option:not([value=""])').first().getAttribute('value');
    test.skip(!agentValue, 'No hay agentes activos para crear el schema desechable.');
    await agentSelect.selectOption(agentValue!);
    await page.getByRole('button', { name: /^Siguiente$/i }).click();

    await page.getByRole('button', { name: /^Nuevo esquema$/i }).click();
    const schemaKey = `e2e_${Date.now()}`;
    await page.getByLabel(/^Clave estable$/i).fill(schemaKey);
    await page.getByLabel(/^Nombre$/i).last().fill(`E2E ${schemaKey}`);
    await page.getByRole('button', { name: /^Crear$/i }).click();
    await expect(page.getByTestId('context-schema-detail')).toBeVisible();

    await page.getByRole('button', { name: /^Agregar campo$/i }).click();
    let fieldForm = page.getByTestId('context-field-form');
    await fieldForm.getByLabel(/^Clave$/i).fill('e2e_field');
    await fieldForm.getByLabel(/^Etiqueta$/i).fill('Campo E2E');
    await fieldForm.getByRole('button', { name: /^Guardar$/i }).click();
    let fieldRow = page.locator('li').filter({ hasText: 'Campo E2E' });
    await expect(fieldRow).toBeVisible();

    await fieldRow.getByRole('button', { name: /^Editar campo$/i }).click();
    fieldForm = page.getByTestId('context-field-form');
    await fieldForm.getByLabel(/^Etiqueta$/i).fill('Campo E2E editado');
    await fieldForm.getByRole('button', { name: /^Guardar$/i }).click();
    fieldRow = page.locator('li').filter({ hasText: 'Campo E2E editado' });
    await expect(fieldRow).toBeVisible();

    await fieldRow.getByRole('button', { name: /^Eliminar campo$/i }).click();
    await page.getByRole('dialog').getByRole('button', { name: /^Eliminar campo$/i }).click();
    await expect(fieldRow).toHaveCount(0);
    await page.getByRole('button', { name: /^Archivar$/i }).click();
    await page.getByRole('dialog').getByRole('button', { name: /^Archivar$/i }).click();
  });

  test('cubre archivado y borrado con una experiencia desechable', async ({ page }) => {
    test.skip(
      process.env.VOICE_EXPERIENCE_E2E_MUTATIONS !== '1',
      'Requiere una experiencia desechable para no archivar/eliminar datos compartidos.'
    );
    await requireAuthenticatedInventory(page);
    const card = page.locator('article').filter({ has: page.getByRole('button', { name: /^Archivar$/i }) }).first();
    test.skip((await card.count()) === 0, 'No hay una experiencia desechable archivable.');
    const name = (await card.locator('h2').innerText()).trim();
    await card.getByRole('button', { name: /^Archivar$/i }).click();
    await page.getByRole('dialog').getByRole('button', { name: /^Archivar$/i }).click();
    await expect(card.getByText('Archivada', { exact: true })).toBeVisible();

    await expect(card.getByRole('button', { name: /^Archivar$/i })).toHaveCount(0);
    await card.getByRole('button', { name: /^Eliminar$/i }).click();
    await page.getByRole('dialog').getByRole('button', { name: /^Eliminar$/i }).click();
    await expect(page.locator('article').filter({ hasText: name })).toHaveCount(0);
  });

  test('sólo permite eliminar experiencias archivadas', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const nonArchivedCard = page
      .locator('article')
      .filter({ hasNot: page.getByText('Archivada', { exact: true }) })
      .first();
    test.skip((await nonArchivedCard.count()) === 0, 'No hay experiencias no archivadas para verificar.');
    await expect(nonArchivedCard.getByRole('button', { name: /^Eliminar$/i })).toHaveCount(0);
  });
});
