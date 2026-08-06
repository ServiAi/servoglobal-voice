import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import enMessages from '../messages/en.json';
import esMessages from '../messages/es.json';
import { resolveVoiceExperienceGateState } from '../lib/permissions/voice-experiences';
import { isVoiceExperienceDirty } from '../lib/voice-experiences/change-detection';
import { getVoiceExperienceErrorKey } from '../lib/voice-experiences/error-messages';
import { isSafeHttpsUrl } from '../lib/voice-experiences/url-safety';
import { createVoiceExperienceDefaults } from '../lib/voice-experiences/validation';

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
    await expect(page.getByTestId('voice-experience-preview')).toBeVisible();
    await expect(page.getByText(/Vista no funcional/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Unirse|Iniciar llamada|Permitir micrófono/i })).toHaveCount(0);

    const accessibility = await new AxeBuilder({ page })
      .include('[data-testid="voice-experience-preview"]')
      .analyze();
    expect(accessibility.violations, JSON.stringify(accessibility.violations, null, 2)).toEqual([]);
  });

  test('despublica con badge traducido y restaura la publicación', async ({ page }) => {
    await requireAuthenticatedInventory(page);
    const card = page.locator('article').filter({ hasText: 'Publicada' }).first();
    test.skip((await card.count()) === 0, 'No hay una experiencia publicada para la regresión.');

    await card.getByRole('button', { name: /^Despublicar$/ }).click();
    await page.getByRole('dialog').getByRole('button', { name: /^Despublicar$/ }).click();
    await expect(card.getByText('Despublicada', { exact: true })).toBeVisible();

    await card.getByRole('button', { name: /^Publicar$/ }).click();
    await page.getByRole('dialog').getByRole('button', { name: /^Publicar$/ }).click();
    await expect(card.getByText('Publicada', { exact: true })).toBeVisible();
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
