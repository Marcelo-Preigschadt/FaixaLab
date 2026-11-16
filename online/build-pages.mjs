import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.dirname(here);
const [destination, codespace, wakeServer] = process.argv.slice(2);
if (!destination || !/^[a-z0-9-]+$/.test(codespace ?? '')) {
  throw new Error('Uso: node online/build-pages.mjs DIRETORIO NOME_DO_CODESPACE [URL_RETOMADA]');
}
if (wakeServer && (new URL(wakeServer).origin !== wakeServer || !wakeServer.startsWith('https://'))) {
  throw new Error('Use a origem HTTPS do serviço de retomada.');
}
const web = path.join(repo, 'app/faixalab/web');
const output = path.resolve(destination);
mkdirSync(output, { recursive: true });
const version = content => createHash('sha256').update(content).digest('hex').slice(0, 12);
for (const asset of ['style.css', 'studio.css', 'mobile.css', 'app.js', 'guitar.js', 'icon.svg', 'icon-192.png', 'icon-512.png']) {
  copyFileSync(path.join(web, asset), path.join(output, asset));
}
const connectionScript = readFileSync(path.join(here, 'pages-connection.js'));
const connectionVersion = version(connectionScript);
writeFileSync(path.join(output, 'pages-connection.js'), connectionScript);
const config = { backend: `https://${codespace}-7861.app.github.dev` };
if (wakeServer) config.wakeServer = wakeServer;
const configScript = 'window.faixaLabPagesConfig = ' + JSON.stringify(config) + ';\n';
writeFileSync(path.join(output, 'pages-config.js'), configScript);

const manifest = JSON.parse(readFileSync(path.join(web, 'manifest.webmanifest'), 'utf8'));
// The original Pages app used its start URL as its browser identity.
delete manifest.id;
manifest.start_url = './';
manifest.scope = './';
manifest.icons.forEach(icon => { icon.src = './' + icon.src.replace(/^\//, ''); });
const webManifest = JSON.stringify(manifest) + '\n';
writeFileSync(path.join(output, 'manifest.webmanifest'), webManifest);

const html = readFileSync(path.join(web, 'index.html'), 'utf8')
  .replace(/\b(href|src)="\//g, '$1="./')
  .replace('href="./style.css"', 'href="./style.css?v=' + version(readFileSync(path.join(web, 'style.css'))) + '"')
  .replace('href="./manifest.webmanifest"', 'href="./manifest.webmanifest?v=' + version(webManifest) + '"')
  .replace('<script src="./app.js" defer></script>',
    '<meta name="referrer" content="no-referrer" />\n    <script src="./pages-config.js?v=' + version(configScript) + '" defer></script>\n    <script src="./pages-connection.js?v=' + connectionVersion + '" defer></script>\n    <script src="./app.js?v=' + version(readFileSync(path.join(web, 'app.js'))) + '" defer></script>')
  .replace('<button\n          id="import-submit"', '<div id="import-google" hidden></div>\n        <button\n          id="import-submit"')
  .replace('Processamento local', 'Processamento online')
  .replace('Suas músicas ficam salvas neste computador.', 'Suas músicas online ficam salvas no servidor.')
  .replace('<main>', `<main>
      <aside id="pages-connection" role="status" hidden>
        <span></span>
        <div id="pages-google" hidden></div>
        <a id="pages-device-action" class="button primary" href="#" hidden></a>
        <button class="button secondary" id="pages-retry" type="button" hidden>Tentar novamente</button>
      </aside>`)
  .replace('<div class="top-actions">', '<div class="top-actions"><button id="pages-signout" class="button secondary" hidden>Sair</button>')
  .replace('</head>', '<style>#pages-connection:not([hidden]){display:flex;gap:12px;align-items:center;justify-content:space-between;padding:12px 16px;background:#1d272a;color:#dde7ea;border-bottom:1px solid #3b4950;flex-wrap:wrap}#pages-connection [hidden],#pages-signout[hidden]{display:none}</style>\n  </head>');
writeFileSync(path.join(output, 'index.html'), html);
const catalog = JSON.parse(execFileSync('python3', ['-c',
  'import json; from faixalab.chord_dictionary import load_dictionary; from faixalab.instrument_catalog import public_catalog; print(json.dumps([load_dictionary(),public_catalog()]))'],
  { encoding: 'utf8', cwd: repo, env: { ...process.env, PYTHONPATH: path.join(repo, 'app') } }));
writeFileSync(path.join(output, 'chord-dictionary.json'), JSON.stringify(catalog[0]) + '\n');
writeFileSync(path.join(output, 'instruments.json'), JSON.stringify(catalog[1]) + '\n');
execFileSync('python3', [path.join(here, 'package-local-import.py'), path.join(output, 'FaixaLab_Importador.zip')]);
writeFileSync(path.join(output, '.nojekyll'), '');
