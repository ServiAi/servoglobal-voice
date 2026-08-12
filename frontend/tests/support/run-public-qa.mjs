import { rmSync } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';

const nextCli = './node_modules/next/dist/bin/next';
const playwrightCli = './node_modules/@playwright/test/cli.js';

async function waitForServer(url) {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.status < 500) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

function stopTree(child) {
  if (!child.pid) return;
  if (process.platform === 'win32') {
    spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    child.kill('SIGTERM');
  }
}

async function runSuite({ port, apiPort, config, project, turnstileMode, webrtcMode }) {
  rmSync('.next', { recursive: true, force: true });
  const server = spawn(process.execPath, [nextCli, 'dev', '-p', String(port)], {
    env: {
      ...process.env,
      NEXT_PUBLIC_API_URL: `http://127.0.0.1:${apiPort}`,
      NEXT_PUBLIC_TURNSTILE_SITE_KEY: turnstileMode === '0' ? '' : process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY,
      NEXT_PUBLIC_VOICE_PUBLIC_TURNSTILE_TEST_MODE: turnstileMode,
      NEXT_PUBLIC_VOICE_PUBLIC_WEBRTC_TEST_MODE: webrtcMode,
    },
    stdio: 'ignore',
  });

  try {
    await waitForServer(`http://127.0.0.1:${port}`);
    const result = spawnSync(process.execPath, [playwrightCli, 'test', `--config=${config}`, `--project=${project}`], {
      env: { ...process.env, PLAYWRIGHT_EXTERNAL_PUBLIC_SERVER: '1' },
      stdio: 'inherit',
    });
    if (result.error) throw result.error;
    if (result.status !== 0) process.exitCode = result.status ?? 1;
  } finally {
    stopTree(server);
  }
}

await runSuite({
  port: 3200,
  apiPort: 43119,
  config: 'playwright.public.config.ts',
  project: 'public',
  turnstileMode: '1',
  webrtcMode: '1',
});

if (!process.exitCode) {
  await runSuite({
    port: 3201,
    apiPort: 43120,
    config: 'playwright.public-no-turnstile.config.ts',
    project: 'public-no-turnstile',
    turnstileMode: '0',
    webrtcMode: '0',
  });
}

process.exit(process.exitCode ?? 0);
