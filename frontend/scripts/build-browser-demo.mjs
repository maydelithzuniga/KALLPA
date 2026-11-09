// Construye la demo que corre 100% en el navegador (Pyodide) en ./dist-static.
// Uso: PYODIDE_DIR=/ruta/a/pyodide node scripts/build-browser-demo.mjs
// PYODIDE_DIR debe contener los archivos de la versión 0.26.4: pyodide.js, pyodide.asm.js, pyodide.asm.wasm,
// python_stdlib.zip, pyodide-lock.json, SQLAlchemy-*.whl, sqlite3-*.zip, tzdata-*.whl, typing_extensions-*.whl
import { execSync } from 'node:child_process'
import { copyFileSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const pyDir = process.env.PYODIDE_DIR
if (!pyDir) { console.error('Define PYODIDE_DIR'); process.exit(1) }
execSync('npx vite build --base ./ --outDir dist-static', { stdio: 'inherit', env: { ...process.env, VITE_STATIC: '1' } })
const out = 'dist-static/py'
mkdirSync(out, { recursive: true })
for (const f of readdirSync(pyDir)) copyFileSync(join(pyDir, f), join(out, /\.(zip|whl)$/.test(f) ? f + '.wasm' : f))
const src = {}
for (const f of readdirSync('../backend/app')) if (f.endsWith('.py')) src[`app/${f}`] = readFileSync(join('../backend/app', f), 'utf8')
src['webapp.py'] = readFileSync('../backend/browser/webapp.py', 'utf8')
writeFileSync(join(out, 'app.json'), JSON.stringify(src))
console.log('Demo del navegador lista en dist-static/')
