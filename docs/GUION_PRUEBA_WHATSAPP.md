# Guion para probar Kallpa por WhatsApp (copiar y pegar, un mensaje a la vez)

Escribe cada línea **como un mensaje aparte** en el chat «Twilio Sandbox» y espera la respuesta.
(Probado con la misma lógica que corre en el servidor. Si activaste Gemini, las palabras pueden variar un poco.)

## 1 · Primera vez: Kallpa conoce tu negocio (sin saber que arma tu inventario)
| Tú escribes | Kallpa responde (más o menos) |
|---|---|
| `hola` | ¡Hola! Soy Kallpa 👋 … ¿Cómo te llamas? |
| `Maydelith` | Mucho gusto, Maydelith. ¿Qué vendes? |
| `verduras: tomate, papa, cebolla y limón` | Anoté: tomate, papa, cebolla, limón. ¿Vendes algo más? |
| `eso es todo` | ¿Cómo vendes casi todo: por kilo, por unidad…? |
| `por kilo, pero el limón por unidad` | (1 de 4) ¿A cuánto das el kilo de tomate? ¿Y a ti cuánto te cuesta? |
| `a 3, me cuesta 2` | (2 de 4) … papa |
| `a 2.50, me cuesta 1.80` | (3 de 4) … cebolla |
| `a 3, me cuesta 2.20` | (4 de 4) ¿A cuánto das la unidad de limón? |
| `a 20 céntimos, me cuesta 10 céntimos` | ¿Cómo compras en el mayorista? |
| `el tomate por jaba de 20 kilos a 40 soles, la papa por saco de 50 kilos a 85 y la cebolla por kilo` | ¿Cuánto te queda ahorita de cada cosa? |
| `1 jaba de tomate, medio saco de papa, 10 kilos de cebolla y 100 limones` | ¿Cómo te pagan: efectivo, Yape o las dos? |
| `las dos` | Ahora tus gastos: ¿qué cosas pagas para tu negocio y cada cuánto? |
| `alquiler del puesto 250 al mes, luz 40 al mes, pasaje 10 al día y bolsas 15 a la semana` | Anoté: Alquiler del puesto S/ 250 al mes (fijo), Luz S/ 40 al mes (fijo), Pasaje S/ 10 al día (fijo), Bolsas S/ 15 a la semana (variable). Al mes son unos S/ 655 (S/ 590 fijos y S/ 65 variables). ¿Pagas algo más? |
| `la licencia 120` | ¿Cada cuánto pagas licencia (S/ 120)? *(si no dices cada cuánto, te pregunta)* |
| `al año` | (lista actualizada) ¿Pagas algo más? |
| `eso es todo` | Última pregunta: cuenta la plata de tu monedero. ¿Cuánto es? |
| `tengo 80 soles en el monedero y 50 en el yape` | Así quedó tu negocio: (lista con precios, costos y lo que te queda) ¿Está bien así? |
| `sí, está bien` | ¡Todo listo, Maydelith! 🎉 |

## 2 · Durante el día: ventas, gastos, fiados y pérdidas (se guarda al toque)
| Tú escribes | Kallpa responde |
|---|---|
| `vendí 3 soles de tomate y un kilo de papa en efectivo` | ✓ S/ 3 tomate · quedan 19 kg, S/ 2.50 papa (1 kg) · quedan 24 kg · efectivo |
| `vendí 2 kilos de cebolla por yape` | ✓ S/ 6 cebolla (2 kg) · Yape (por verificar) |
| `deshacer` | Listo, lo borré |
| `vendí 2 kilos de cebolla por yape` | ✓ S/ 6 cebolla (2 kg) · Yape |
| `vendí medio kilo de tomate y 10 limones` | ¿Te pagaron en efectivo o por Yape? *(pregunta solo lo que falta)* |
| `efectivo` | ✓ S/ 1.50 tomate (½ kg), S/ 2 diez limones · efectivo |
| `gasté 5 soles en bolsas` | Gasto del negocio: bolsas, S/ 5. ¿Salió del efectivo o del Yape? |
| `yape` | ✓ gasto S/ 5 bolsas y empaques · Yape |
| `Rosa se llevó 2 kilos de papa fiado` | ✓ S/ 5 papa (2 kilos) · te debe S/ 5 (Rosa) |
| `se malogró un kilo de tomate` | ✓ pérdida S/ 2 · tomate (malogrado) · lo resté de tu ganancia |
| `en esta última hora vendí como 30 soles en efectivo` | ✓ S/ 30 ventas varias · efectivo |
| `Rosa me pagó 5 soles` | Rosa te pagó S/ 5 del fiado. ¿Efectivo o Yape? |
| `efectivo` | ✓ Rosa te pagó S/ 5 · ya no te debe nada |

## 3 · Preguntas
| Tú escribes | Kallpa responde |
|---|---|
| `resumen` | Tu día: vendiste S/ 50 (Yape, efectivo, fiado)… ganancia… pérdidas… caja |
| `cuánto tengo` | En caja tienes S/ 175 (S/ 124 efectivo, S/ 51 Yape) |
| `cuánto tomate me queda` | Tomate: 17.5 kilos |
| `qué es el flujo de caja` | Explicación con TUS números de la semana |
| `qué es la ganancia` / `qué es el margen` | Con tus ventas y costos reales |
| `cuánto tengo que vender` | Te pide tus gastos fijos si aún no los sabe |
| `pago 250 de alquiler al mes` / `bolsas 15 a la semana` | ✓ Anoté tu gasto: … (fijo / variable). Necesitas vender S/ … al día |
| `qué es la rotación` | Cuánto tienes en mercadería y (con una semana de datos) en cuántos días la vendes |
| `quiero ahorrar 300 soles para fin de mes` | Meta guardada |
| `ayuda` | Ejemplos con tus productos |

## 4 · Cierre del día (contando la plata)
| Tú escribes | Kallpa responde |
|---|---|
| `cerrar mi día` | Hoy registraste S/ 50… cuenta la plata de tu monedero: ¿cuánto tienes? |
| `tengo 150 en efectivo` | Esperaba S/ 124: te sobran S/ 26. ¿Las guardo como ventas en efectivo? |
| `sí, guárdalas` | Guardé S/ 26… ¿Tuviste alguna pérdida hoy? |
| `no, nada` | Listo, tu día está cerrado. Vendiste S/ 76 y ganaste S/ 55.20… revisa 2 Yapes por verificar |

## 5 · Lista para cobrar (te llega a ti, no a la clienta)
| Tú escribes | Kallpa responde |
|---|---|
| `Juan se llevó un kilo de cebolla fiado` | ✓ S/ 3 cebolla (1 kilo) · te debe S/ 3 (Juan) |
| `a quién tengo que cobrar` | Por cobrar (S/ 3): Juan S/ 3, de hoy. |

## Si vendes ropa (u otro rubro)
| Tú escribes | Kallpa responde |
|---|---|
| `Vendo ropa` | ¡Qué bien! ¿Qué prendas vendes más? Dime 3 o 4 |
| `polos, blusas y pantalones` | Anoté: polo, blusa, pantalón |
| `eso es todo` → `por unidad` | ¿A cuánto das la unidad de polo? ¿Y a ti cuánto te cuesta? |
| `a 25, me cuesta 12` / `a 30, me cuesta 15` / `a 50, me cuesta 28` | (una pregunta por prenda) |
| `los polos por docena a 144, lo demás por unidad` | ¿Cuánto te queda ahorita? |
| `20 polos, 15 blusas y 10 pantalones` → `las dos` | Ahora tus gastos: ¿qué pagas y cada cuánto? |
| `alquiler 300 el 5 de cada mes y bolsas 20 a la semana` → `eso es todo` | Alquiler S/ 300 al mes (fijo), Bolsas S/ 20 a la semana (variable) |
| `tengo 100 en efectivo y 60 en yape` → `sí` | ¡Todo listo! |
| `vendí 2 polos y una blusa por yape` | ✓ S/ 50 dos polos, S/ 30 una blusa · Yape |
| `vendí un pantalón en efectivo` | ✓ S/ 50 un pantalón · efectivo (usa tu precio, sin preguntar) |
| `Carmen se llevó una blusa fiado` | ✓ S/ 30 una blusa · te debe S/ 30 (Carmen) |
| `se me perdió un polo` | ✓ pérdida S/ 12 · polo |

## 6 · Audios
Manda un **audio** diciendo: «vendí dos kilos de papa y un kilo de cebolla en efectivo».
Kallpa responde con lo que entendió (🎙️ «…») y lo guarda. Necesita `AGENT_ENABLED=true` y `GEMINI_API_KEY` en Render.

## Después: míralo en la app
Abre https://kallpa-kzc2.onrender.com → tu negocio (con tu nombre) → Inicio, Mis números, Historial, Informe BCP.
