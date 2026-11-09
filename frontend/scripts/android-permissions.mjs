// Agrega los permisos de micrófono e internet al AndroidManifest generado por Capacitor.
import { readFileSync, writeFileSync, existsSync } from 'node:fs'

const path = 'android/app/src/main/AndroidManifest.xml'
if (!existsSync(path)) {
  console.error('No existe', path, '- ejecuta primero: npx cap add android')
  process.exit(1)
}
let xml = readFileSync(path, 'utf8')
const perms = [
  'android.permission.INTERNET',
  'android.permission.RECORD_AUDIO',
  'android.permission.MODIFY_AUDIO_SETTINGS',
  'android.permission.ACCESS_NETWORK_STATE',
]
for (const p of perms) {
  if (!xml.includes(p)) {
    xml = xml.replace('</manifest>', `    <uses-permission android:name="${p}" />\n</manifest>`)
  }
}
if (!xml.includes('usesCleartextTraffic')) {
  xml = xml.replace('<application', '<application android:usesCleartextTraffic="true"')
}
writeFileSync(path, xml)
console.log('Permisos de micrófono e internet agregados a', path)
