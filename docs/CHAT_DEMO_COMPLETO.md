# Chat de demostración completo de Kallpa (WhatsApp o chat de la app)

Probado mensaje por mensaje con la misma lógica del servidor: **66 mensajes, 0 «no te entendí»**.
Escribe cada línea de la columna izquierda **como un mensaje aparte** y espera la respuesta.
Las respuestas con IA (audios y coach) pueden variar en palabras; los registros y números son los mismos.

## Antes de empezar
1. Abre https://kallpa-kzc2.onrender.com 2 minutos antes (el servidor gratis se duerme).
2. En WhatsApp: `empezar de nuevo` → `sí, borrar todo` (empieza limpio). Si hace más de 3 días: `join tobacco-hard`.
3. Para audios y coach con IA: en Render, `AGENT_ENABLED=true` y `GEMINI_API_KEY`.

## Acto 1 · Conoce el negocio sin formularios: inventario, precios, costos, gastos y plata

| Tú escribes | Kallpa responde |
|---|---|
| `hola` | ¡Hola! Soy Kallpa 👋 Te ayudo a llevar las cuentas de tu negocio con mensajes de voz, sin cuadernos. Primero quiero conocerte un poquito. ¿Cómo te llamas? |
| `Juana` | Mucho gusto, Juana. ¿Qué vendes? Cuéntamelo como a una amiga, por ejemplo «verduras: tomate, papa, cebolla y limón». |
| `vendo verduras: tomate, papa, cebolla y limón` | Anoté: tomate, papa, cebolla, limón. ¿Vendes algo más? Dime qué, o «eso es todo». |
| `también culantro` | Anoté: tomate, papa, cebolla, limón, culantro. ¿Vendes algo más? Dime qué, o «eso es todo». |
| `eso es todo` | ¿Cómo vendes casi todo: por kilo, por unidad, por atado o de a sol (en montoncitos)? Si algo es distinto, dímelo, por ejemplo «por kilo, pero el culantro por atado». |
| `por kilo, pero el limón por unidad y el culantro por atado` | (1 de 5) ¿A cuánto das el kilo de tomate? ¿Y a ti cuánto te cuesta? Por ejemplo «a 4, me cuesta 2.50». |
| `a 3, me cuesta 2` | (2 de 5) ¿A cuánto das el kilo de papa? ¿Y a ti cuánto te cuesta? Por ejemplo «a 4, me cuesta 2.50». |
| `a 2.50, me cuesta 1.80` | (3 de 5) ¿A cuánto das el kilo de cebolla? ¿Y a ti cuánto te cuesta? Por ejemplo «a 4, me cuesta 2.50». |
| `a 3, me cuesta 2.20` | (4 de 5) ¿A cuánto das la unidad de limón? ¿Y a ti cuánto te cuesta? Por ejemplo «a 4, me cuesta 2.50». |
| `a 20 céntimos, me cuesta 10 céntimos` | (5 de 5) ¿A cuánto das el atado de culantro? ¿Y a ti cuánto te cuesta? Por ejemplo «a 4, me cuesta 2.50». |
| `a 1, me cuesta 50 céntimos` | ¿Cómo compras en el mayorista? Por ejemplo «el tomate por jaba de 20 kilos a 50 soles, la papa por saco de 50 kilos». Si compras por kilo, dime «por kilo». |
| `el tomate por jaba de 20 kilos a 40 soles, la papa por saco de 50 kilos a 85 y la cebolla por kilo` | ¿Cuánto te queda ahorita de cada cosa, más o menos? Por ejemplo «2 jabas de tomate, medio saco de papa y 5 kilos de cebolla». Si no sabes, di «no sé». |
| `1 jaba de tomate, medio saco de papa, 10 kilos de cebolla, 100 limones y 20 atados de culantro` | ¿Cómo te pagan tus clientes: en efectivo, por Yape o de las dos formas? |
| `las dos` | Ahora tus gastos: ¿qué cosas pagas para tu negocio y cada cuánto? Por ejemplo «alquiler del puesto 250 al mes, luz 40 al mes, pasaje 10 al día, bolsas 15 a la semana, licencia 120 al año». Si no pagas nada aparte de tu mercadería, di «nada». |
| `alquiler del puesto 250 al mes, luz 40 al mes, pasaje 10 al día y bolsas 15 a la semana` | Anoté: / • Alquiler del puesto S/ 250 al mes (fijo) / • Luz S/ 40 al mes (fijo) / • Pasaje S/ 10 al día (fijo) / • Bolsas S/ 15 a la semana (variable) / Al mes son unos S/ 655 (S/ 590 fijos y S/ 65 variables). / (Fijo = lo pagas vendas o no (alquiler, luz, celular). Variable = sube cuando vendes más (bolsas, flete).) /… |
| `la licencia 120` | ¿Cada cuánto pagas licencia (S/ 120)? |
| `al año` | Anoté: / • Alquiler del puesto S/ 250 al mes (fijo) / • Luz S/ 40 al mes (fijo) / • Pasaje S/ 10 al día (fijo) / • Bolsas S/ 15 a la semana (variable) / • Licencia S/ 120 al año (fijo) / Al mes son unos S/ 665 (S/ 600 fijos y S/ 65 variables). / (Fijo = lo pagas vendas o no (alquiler, luz, celular). Variable = sube cuando… |
| `eso es todo` | Última pregunta: cuenta la plata que tienes ahora en tu monedero. ¿Cuánto es? Si también sabes cuánto tienes en Yape, dímelo. |
| `tengo 80 soles en el monedero y 50 en el yape` | Listo, Juana. Así quedó tu negocio: / • Tomate: lo vendes a S/ 3 el kilo, te cuesta S/ 2, compras por jaba de 20 kg, te quedan 1 jaba / • Papa: lo vendes a S/ 2.50 el kilo, te cuesta S/ 1.80, compras por saco de 50 kg, te quedan ½ saco / • Cebolla: lo vendes a S/ 3 el kilo, te cuesta S/ 2.20, te quedan 10 kilos / • Limón: lo… |
| `el tomate es a 3.50` | Corregido. Listo, Juana. Así quedó tu negocio: / • Tomate: lo vendes a S/ 3.50 el kilo, te cuesta S/ 2, compras por jaba de 20 kg, te quedan 1 jaba / • Papa: lo vendes a S/ 2.50 el kilo, te cuesta S/ 1.80, compras por saco de 50 kg, te quedan ½ saco / • Cebolla: lo vendes a S/ 3 el kilo, te cuesta S/ 2.20, te quedan 10 kilos… |
| `sí` | ¡Todo listo, Juana! 🎉 Ya tengo tu lista de productos y tu caja. Desde ahora, cuando vendas algo mándame un audio, por ejemplo «vendí 3 soles de tomate y un kilo de papa en efectivo». Se guarda al toque. En la noche dime «cerrar mi día» y cuadramos tu plata. / 🎯 Ahora lo más importante: ponerte una meta. Con una meta separas… |

## Acto 2 · Metas propuestas con sus números

| Tú escribes | Kallpa responde |
|---|---|
| `¿por qué la 1?` | Es lo que te cuesta volver a llenar tu puesto (tomate, papa, cebolla…). Si la juntas, nunca te quedas sin mercadería ni tienes que pedir prestado o comprar fiado más caro. ¿La empezamos? |
| `la 2` | ✓ ¡Meta guardada! «Mis gastos fijos del mes»: S/ 600 para el 1 de diciembre, separando S/ 27.27 al día. Te cuento cómo vas en tu resumen de la noche. Para guardar plata en tu meta dime «guardé 10 para mi meta». |

## Acto 3 · Un día de venta, escribiendo (se guarda al toque)

| Tú escribes | Kallpa responde |
|---|---|
| `vendí un kilo de tomate y un kilo de papa en efectivo` | ✓ S/ 3.50 tomate (1 kg) · quedan 19 kg, S/ 2.50 papa (1 kg) · quedan 24 kg · efectivo |
| `vendí 2 kilos de cebolla y 5 limones por yape` | ✓ S/ 6 cebolla (2 kg) · quedan 8 kg, S/ 1 cinco limones · quedan 95 · Yape (por verificar) |
| `vendí 2 atados de culantro` | ¿Te pagaron en efectivo o por Yape? |
| `efectivo` | ✓ S/ 2 culantro (2 atados) · quedan 18 atados · efectivo |
| `deshacer` | Listo, lo borré: S/ 2 culantro (2 atados) · quedan 18 atados. |
| `corrige, el tomate fue 4 soles` | Corregido. Quedó: tomate, S/ 4 en efectivo. Guardé el cambio en el historial. |
| `gasté 5 soles en bolsas` | Gasto del negocio: bolsas y empaques, S/ 5. ¿Salió del efectivo o del Yape? |
| `yape` | ✓ gasto S/ 5 bolsas y empaques · Yape (por verificar) |
| `Rosa se llevó 2 kilos de papa fiado` | ✓ S/ 5 papa (2 kilos) · te debe S/ 5 (Rosa) · quedan 22 kg |
| `la señora Carmen se llevó medio kilo de tomate fiado` | ✓ S/ 1.75 tomate (½ kilo) · te debe S/ 1.75 (Carmen) · quedan 18.5 kg |
| `se malogró un kilo de tomate` | ✓ pérdida S/ 2 · tomate (1 kilo) (malogrado) · lo resté de tu ganancia |
| `en esta última hora vendí como 30 soles en efectivo` | ✓ S/ 30 ventas varias · efectivo |
| `Rosa me pagó 5 soles` | Rosa te pagó S/ 5 del fiado. ¿Entró en efectivo o por Yape? |
| `efectivo` | ✓ Rosa te pagó S/ 5 · efectivo · ya no te debe nada |
| `me saqué 20 para la casa` | Para la casa: S/ 20. No cuenta como gasto del negocio. ¿Salió del efectivo o del Yape? |
| `efectivo` | ✓ S/ 20 para la casa · efectivo |
| `compré una jaba de tomate a 40 en efectivo` | ✓ compra S/ 40 tomate (1 jaba) · efectivo |
| `cuánto tomate me queda` | Según tus registros te queda: Tomate: 37.5 kilos. |

## Acto 4 · Por audio 🎙️ (notas de voz)

| Dices (nota de voz) | Kallpa responde |
|---|---|
| «Vendí dos kilos de papa y un kilo de cebolla en efectivo» | 🎙️ «vendí 2 kilos de papa…» ✓ S/ 5 papa (2 kg), S/ 3 cebolla (1 kg) · efectivo |
| «La señora Carmen se llevó medio kilo de tomate fiado» | ✓ S/ 1.75 tomate (½ kilo) · te debe S/ 1.75 (Carmen) |
| «¿Cómo consigo más clientes?» | Respuesta del coach con tus números y «👉 Hoy:» |

## Acto 5 · Preguntas sobre sus números

| Tú escribes | Kallpa responde |
|---|---|
| `¿cuánto vendí hoy?` | Tu día, lunes 9: vendiste S/ 50.25 (S/ 7 Yape, S/ 36.50 efectivo, S/ 6.75 fiado). Te pagaron S/ 5 de fiados. Compraste mercadería por S/ 40. Gastaste S/ 5 del negocio. Ganancia del día: S/ 29.95. Sacaste S/ 20 para la casa. Tuviste pérdidas por S/ 2. En caja tienes S/ 113.50 disponibles (S/ 61.50 efectivo, S/ 52 Yape). Vas… |
| `cuánto tengo` | En caja tienes S/ 113.50 disponibles (S/ 61.50 efectivo, S/ 52 Yape). |
| `qué es el flujo de caja` | Es la plata que de verdad tienes en la mano para usar. Esta semana vendiste S/ 50.25, pero S/ 6.75 te los deben de fiado y pagaste S/ 45 en compras y gastos y sacaste S/ 20 para la casa. Así que salió más plata de la que entró: S/ 16.50 menos. Es normal si compraste mercadería (S/ 40): esa plata vuelve cuando la vendas. |
| `qué es el margen` | Es cuánto te queda de cada venta después de pagar lo que te costó. Por ejemplo, tomate: lo vendes en promedio a S/ 3.83 y te deja S/ 1.83 por unidad (47.8%). |
| `cuánto tengo que vender` | Es lo mínimo que tienes que vender para no perder: lo que cubre tus gastos fijos del mes. Tus gastos fijos son S/ 600 al mes y de cada sol que vendes te quedan 64 céntimos para cubrirlos. Necesitas vender S/ 943.66 al mes, unos S/ 31.46 al día. |
| `a quién tengo que cobrar` | Por cobrar (S/ 1.75): Carmen S/ 1.75, de hoy. |

## Acto 6 · Meta propia guiada y ahorro

| Tú escribes | Kallpa responde |
|---|---|
| `quiero otra meta` | ¡Me encanta que quieras ponerte una meta! 🎯 ¿Para qué quieres juntar plata? Por ejemplo «una congeladora», «reponer mercadería», «un colchón para emergencias». |
| `una congeladora` | ¿Cuánto necesitas juntar para congeladora? Dime el monto aproximado, por ejemplo «1500». |
| `1500` | ¿Para cuándo la necesitas? |
| `en 3 meses` | ✓ Meta guardada: «Congeladora», S/ 1,500 para el 7/2. Para llegar el 7/2 separa S/ 16.67 al día (S/ 116.69 a la semana). Es el 168% de lo que ganas al mes — es bastante. / Para llegar: al cerrar cada día, dime «separé 10 para mi meta»; vende más tomate, que te deja S/ 1.50 por unidad; cobra los S/ 1.75 que te deben. |
| `separé 10 para la congeladora` | Separas S/ 10 para «Congeladora». ¿Salió del efectivo o del Yape? |
| `efectivo` | ✓ S/ 10 para «Congeladora» · efectivo · vas al 1% |

## Acto 7 · Asesor financiero: consejos y préstamos

| Tú escribes | Kallpa responde |
|---|---|
| `dame consejos` | 💡 Mis consejos para tu negocio: / 1. Papa te deja S/ 0.70 por kilo y limón solo S/ 0.10 por unidad: ofrece más papa. / 2. Tus gastos fijos son S/ 600 al mes (S/ 20 al día). Con tus márgenes necesitas vender unos S/ 50.51 al día para cubrirlos. / 3. Te deben S/ 1.75 de fiados: cóbralos antes de fiar más; es plata tuya que no… |
| `¿cuánto me prestarían?` | Producto que te conviene: crédito para capital de trabajo, según lo que registras (estimado). Podrías pagar una cuota de hasta S/ 89.55 al mes: un préstamo de unos S/ 490 a 6 meses o S/ 900 a 12 meses. Úsalo para comprar por volumen o equipar tu puesto, no para gastos de la casa. Escribe «informe» y llévalo al banco. / Antes… |
| `puedo pedir un crédito de 2000?` | Un préstamo de S/ 2,000 a 12 meses sería una cuota de unos S/ 199.05 al mes (tasa referencial 40% anual). ⚠️ Es más de lo prudente para ti (hasta S/ 89.55 al mes). Mejor pide unos S/ 900 o junta una parte primero. / Antes de pedir: compara la TCEA (el costo total) entre bancos y cajas, pide solo para algo que te haga ganar… |

## Acto 8 · Coach de negocios para MYPES

| Tú escribes | Kallpa responde |
|---|---|
| `¿cómo consigo más clientes?` | • Ofrece primero lo que más te deja: tomate (S/ 1.50 por unidad). / • Atiende rápido y con Yape a la vista (QR impreso): muchos clientes eligen donde pagar es fácil. / • Pide el número a tus caseras y avisa por WhatsApp cuando llega mercadería fresca. / 👉 Hoy: pega tu QR de Yape en un lugar visible. |
| `¿subo el precio del tomate?` | Tomate: precio S/ 3.50, costo S/ 2, te deja 43%. / • Tu margen está sano: antes de subir, mira el precio de tus vecinas; mejor ofrécelo en combo. / • Si subes, hazlo de a poco y en un producto a la vez; mira si tus ventas bajan esa semana. / 👉 Hoy: anota el precio de 2 vecinas para tu producto principal. |
| `mi vecina vende más barato, ¿qué hago?` | • No entres a una guerra de precios: compite con frescura, atención, yapa y Yape. / • Ofrece primero lo que más te deja: tomate (S/ 1.50 por unidad). / • Atiende rápido y con Yape a la vista (QR impreso): muchos clientes eligen donde pagar es fácil. / • Pide el número a tus caseras y avisa por WhatsApp cuando llega… |
| `¿debo sacar RUC?` | • Para negocios pequeños existe el Nuevo RUS: pagas una cuota fija al mes y emites boletas simples. / • Tener RUC te ayuda a vender a empresas y a pedir créditos con mejores condiciones. / • Confirma tu categoría en SUNAT (sunat.gob.pe) o en una oficina; es un trámite gratuito. / 👉 Hoy: averigua en la web de SUNAT los… |
| `¿cómo separo la plata de la casa?` | • Ganas unos S/ 298.50 al mes: separa S/ 2 cada día al cerrar (20%). / • Págate un sueldo fijo para la casa y anótalo como «para la casa»: así no mezclas plata. / • Te deben S/ 1.75: cobrar eso es la plata más barata que tienes. / 👉 Hoy: dime al cerrar «separé 10 para mi meta». |

## Acto 8b · Preguntas teóricas de finanzas, explicadas sencillo y con sus números

| Tú escribes | Kallpa responde |
|---|---|
| `qué son gastos fijos` | 📘 Gastos fijos: son los pagos que haces igual, vendas mucho o poco… Ejemplo: … En tu negocio: tus gastos fijos son alquiler del puesto, luz…: S/ 600 al mes (S/ 20 al día). |
| `diferencia entre gastos fijos y variables` | 📘 Gastos fijos… 📘 Gastos variables… (los dos, con sus números) |
| `¿qué es la TCEA?` | 📘 TCEA: cuánto te cuesta DE VERDAD un préstamo… compara la más baja… En tu negocio: podrías pagar hasta S/ … de cuota |
| `¿qué es el capital de trabajo?` | 📘 … En tu negocio: tienes S/ … en caja, S/ … en mercadería y S/ … por cobrar |
| `¿qué es la central de riesgo?` | 📘 Registro de cómo pagas (SBS, Infocorp, Sentinel)… |
| `¿qué es el leasing?` | 📘 Leasing: alquilar un equipo pagando cuotas y al final quedártelo… |

Más de 40 conceptos en el glosario (gastos fijos y variables, margen, ganancia, flujo, capital de trabajo, punto de
equilibrio, liquidez, rotación, merma, TCEA/TEA, cuota, central de riesgo, garantía, sobreendeudamiento, «gota a gota»,
ahorro, interés compuesto, inflación, presupuesto, inversión, IGV, RUC/Nuevo RUS, boleta/factura, leasing, factoring,
línea de crédito, tarjeta de crédito, refinanciar, periodo de gracia, cajas y cooperativas, seguros…).
Si preguntan algo que no está, Kallpa consulta a Gemini con búsqueda de Google y, si no responde, la API de Wikipedia.

## Acto 9 · Informe para el banco

| Tú escribes | Kallpa responde |
|---|---|
| `informe` | 📄 Tu informe financiero para el banco (solo lo verificado por Yape). Todavía no tienes movimientos por Yape verificados: el informe solo usa lo verificado. Cobra por Yape y verifica tus Yape en la app (Más → Historial) para que se llene. Lo descargas en la app, en «Informe BCP». |

## Acto 9b · Fin de mes: ¿enviamos tu informe a los bancos aliados? (sí o sí)

Cada fin de mes Kallpa pregunta (al cerrar el día, en el aviso de la noche y, si no responde, una vez al día hasta que
decida). Para mostrarlo en la demo sin esperar al último día: en la app, **Más → Ajustes → Mensajes automáticos →
«Fin de mes: informe a los bancos»**, o usa un negocio de ejemplo (ya tiene el mes anterior pendiente).

| Tú escribes | Kallpa responde |
|---|---|
| `resumen` | (resumen) … 📊 Tu informe de finanzas de octubre está listo (solo lo verificado por Yape). ¿Quieres que lo enviemos a nuestros bancos aliados (BCP) para que conozcan tu negocio y puedan ofrecerte productos financieros…? Tú decides cada mes. [Sí, envíalo · No por ahora · ¿Qué se envía?] |
| `¿qué se envía?` | Se envía tu informe financiero en PDF: ingresos y egresos por Yape verificados, flujo neto, cuota posible, estabilidad y clientes. No se envía tu efectivo ni tus conversaciones… |
| `sí` | ✓ Listo. Enviamos tu informe de octubre a BCP (simulado). Código KAL-… Te dejo tu copia (PDF adjunto). Si un banco tiene una oferta para ti, te aviso por aquí. |

Los bancos aliados se configuran en Render con `PARTNER_BANKS` (por ejemplo `BCP, Mibanco`).

## Acto 10 · Cierre del día contando la plata

| Tú escribes | Kallpa responde |
|---|---|
| `cerrar mi día` | Vamos a cerrar tu día. Hoy registraste S/ 50.25 en ventas: S/ 41.50 en efectivo y S/ 7 por Yape. Ahora cuenta la plata de tu monedero: ¿cuánto tienes? |
| `tengo 70 en efectivo` | Tienes S/ 70 y yo esperaba S/ 51.50: te sobran S/ 18.50. Seguro son ventas que no alcanzaste a dictar. ¿Las guardo como ventas en efectivo de hoy? |
| `sí, guárdalas` | Guardé S/ 18.50 como ventas en efectivo de hoy. ¿Tuviste alguna pérdida hoy? Algo que se malogró, se venció, se rompió o te robaron. Dime qué y cuánto, o «no». |
| `no, nada` | Listo, tu día está cerrado. Hoy vendiste S/ 68.75 y ganaste S/ 48.45. Perdiste S/ 2 en mercadería o cosas malogradas. Vas al 0% de tu meta «Mis gastos fijos del mes». / Por cobrar (S/ 1.75): Carmen S/ 1.75, de hoy. Tienes S/ 70 en efectivo y S/ 52 en Yape. Revisa en tu Yape 3 movimientos de hoy (S/ 12) que aún no están… |

## Acto 11 · En la app

Abre https://kallpa-kzc2.onrender.com → negocio de Juana (lo mismo que conversaste):
- **Inicio**: ¿cuánto cobré hoy?, ¿cuánto tengo?, ¿cuánto puedo usar para reponer?
- **Mis números**: semana, a quién cobrar, consejos y «Ver gráficos».
- **Más → Historial**: cada movimiento; los de Yape se verifican.
- **Más → Informe BCP → «📄 Informe formal para el banco (PDF)»** (mejor con un negocio de ejemplo, que tiene meses de Yape verificados).
- **Más → Ajustes → Lo que pagas en tu negocio**: gastos con frecuencia, fijo/variable y total al mes.
- **Metas**: las metas que eligió por WhatsApp.

## Si algo falla en vivo
- No responde en 1 minuto → el servidor estaba dormido: manda el mensaje otra vez.
- «not connected to the sandbox» → `join tobacco-hard`.
- Plan B: el mismo chat dentro de la app (pestaña Dictar) hace todo igual.
