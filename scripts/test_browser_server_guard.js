const { spawn, spawnSync } = require('node:child_process');

const port = 4173;
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function main() {
  const server = spawn('python3', [
    '-m', 'http.server', String(port), '--bind', '127.0.0.1', '--directory', 'verified-site',
  ], { stdio: ['ignore', 'pipe', 'pipe'] });
  let serverOutput = '';
  let serverError = '';
  server.stdout.setEncoding('utf8');
  server.stdout.on('data', chunk => { serverOutput += chunk; });
  server.stderr.setEncoding('utf8');
  server.stderr.on('data', chunk => { serverError += chunk; });

  try {
    let ready = false;
    for (let attempt = 0; attempt < 50; attempt += 1) {
      if (server.exitCode !== null) {
        throw new Error(`Cannot run occupied-port regression; leaving any preexisting listener untouched. ${serverError.trim()}`);
      }
      try {
        const response = await fetch(`http://127.0.0.1:${port}/quick-reference/`);
        ready = response.ok && (await response.text()).includes('Quick Reference');
        if (ready && `${serverOutput}${serverError}`.includes('GET /quick-reference/')) break;
        ready = false;
      } catch (_) {
        // Wait briefly for this test-owned server to bind the port.
      }
      await delay(100);
    }
    if (!ready) throw new Error(`Test-owned server did not become ready on ${port}: ${serverError}`);

    const result = spawnSync('npx', [
      'playwright', 'test', '--grep', 'accessibility failure is detected by the same fail-closed gate',
    ], { encoding: 'utf8', timeout: 90_000 });
    const output = `${result.stdout || ''}\n${result.stderr || ''}`;
    if (result.error) throw result.error;
    if (result.status === 0) {
      throw new Error(`Playwright unexpectedly reused occupied port ${port}; fail-closed server guard is broken.`);
    }
    if (!/address already in use|EADDRINUSE|127\.0\.0\.1:4173.{0,80}already used|port 4173.{0,48}(?:used|occupied)/i.test(output)) {
      throw new Error(`Playwright failed for a reason other than the occupied port:\n${output}`);
    }
    process.stdout.write(`PASS: Playwright rejected test-owned occupied port ${port}; no existing listener was terminated.\n`);
  } finally {
    if (server.exitCode === null && server.pid) {
      server.kill('SIGTERM');
      await Promise.race([
        new Promise(resolve => server.once('exit', resolve)),
        delay(3000),
      ]);
    }
  }
}

main().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
