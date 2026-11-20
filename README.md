# Pizarra Virtual

<img src="assets/pizarra.png" alt="Icono de Pizarra Virtual" width="96" align="right">

**Pizarra Virtual** es una aplicación de escritorio para **Windows 10 y Windows 11** que coloca una
pizarra transparente **sobre todo el escritorio**. Puedes dibujar, subrayar y señalar encima de
cualquier ventana o programa abierto (presentaciones, PDF, navegador, vídeos, código…), con
herramientas parecidas a las de un editor de imagen sencillo, y guardar capturas de pantalla con o
sin lo que has dibujado.

Está pensada para **dar clase y presentar**: texto, foco, cortina, puntero láser, zoom, resaltado del
cursor y de los clics, pautas de escritura (cuadrícula, rayado, caligrafía, plano cartesiano,
pentagrama), varias páginas, guardado de la clase y exportación a PDF.

Se distribuye como un **`.zip`** con el ejecutable **`PizarraVirtual.exe`** (no necesita instalación) y
el **Manual de usuario** en PDF.

---

## Índice

1. [Características](#características)
2. [Descargar](#descargar)
3. [Cómo se usa](#cómo-se-usa)
4. [Atajos de teclado](#atajos-de-teclado)
5. [Capturas de pantalla](#capturas-de-pantalla)
6. [Compilar el .exe](#compilar-el-exe)
7. [Ejecutar desde el código fuente y pruebas](#ejecutar-desde-el-código-fuente-y-pruebas)
8. [Stack tecnológico y justificación](#stack-tecnológico-y-justificación)
9. [Compatibilidad: Windows 10/11, DPI y varios monitores](#compatibilidad-windows-1011-dpi-y-varios-monitores)
10. [Estructura del proyecto](#estructura-del-proyecto)
11. [Solución de problemas](#solución-de-problemas)
12. [Licencia](#licencia)

---

## Características

| Herramienta | Descripción |
|---|---|
| **Lienzo sobre el escritorio** | Ventana transparente, siempre visible y sin bordes que cubre cada monitor. Se activa y desactiva con **Ctrl+Alt+D** o con el botón **Dibujando / Ratón libre** de la barra. En «Ratón libre» los dibujos siguen visibles pero los clics llegan a las ventanas de debajo. **Ctrl+Alt+H** oculta o muestra la pizarra. |
| **Pincel** | Tamaño ajustable (1–150 px) y cuatro tipos: **Duro** (borde nítido), **Suave** (bordes difuminados), **Aerógrafo** (spray) y **Caligráfico** (punta plana inclinada). |
| **Lápiz** | Trazo fino (1–8 px) con tamaño ajustable. |
| **Pluma** | Trazo preciso que imita una pluma estilográfica: curva suave con bordes limpios, **estabilizador** que elimina el temblor del ratón, **entrada y salida afinadas** y final exacto donde se suelta. Con una **tableta o lápiz con sensor de presión** (Wacom, Surface Pen, Windows Ink…) usa la presión real; **sin tableta, la presión se simula con la velocidad del trazo** (despacio = trazo pleno, rápido = más fino, con cambios graduales). El grosor también varía ligeramente con la dirección, como un plumín inclinado. |
| **Destacador** | Trazo ancho y semitransparente (40 % por defecto) con punta biselada, pensado para resaltar texto. No se oscurece al repasar dentro del mismo trazo. |
| **Goma de borrar** | Borra píxeles de los trazos con tamaño ajustable (4–250 px). Con un lápiz de tableta, el extremo «goma» del lápiz borra automáticamente. |
| **Figuras** | **Rectángulo/cuadrado**, **elipse/círculo**, **triángulo**, **línea** y **flecha**, dibujadas arrastrando el cursor. Con **Mayús** se fuerzan proporciones iguales (cuadrado, círculo) o ángulos de 15° (líneas y flechas). Las figuras cerradas se pueden **rellenar**. |
| **Más figuras** | Botón con menú: **pentágono**, **hexágono**, **octágono** (P), **rombo** (D), **estrella** (E), **rectángulo redondeado** (Q), **ejes de coordenadas** (J), **flecha doble** (W), **flecha curva** (U) y **llave** (K). |
| **Sellos** | Tecla **S** o botón con menú: **✔ correcto**, **✘ incorrecto**, **estrella**, **carita feliz**, **números** (1, 2, 3… que siguen la cuenta en cada página) e **interrogación**. Un clic pone el sello; el cursor muestra la vista previa. |
| **Plantillas** | Botón con menú: **mapa conceptual**, **línea de tiempo**, **diagramas de Venn** (2 y 3 conjuntos), **tabla de dos columnas**, **tabla S-Q-A**, **esquema de redacción**, **ciclo** y **causa y efecto**. Se insertan y se quitan de una vez (Ctrl+Z); cada rótulo se edita con un clic. |
| **Formas perfectas** | Opción que se **activa o desactiva** (botón con pincel, lápiz o pluma, o tecla **G**; desactivada por defecto): al soltar el trazo, las rectas, círculos, elipses, rectángulos y polígonos dibujados a mano se convierten en figuras exactas. Lo demás queda tal cual. |
| **Seleccionar y mover** | Tecla **A**: clic en un elemento o lazo para seleccionar; arrastrar para mover y la esquina para cambiar el tamaño. **Supr** elimina, **Ctrl+D** duplica, **Ctrl+A** selecciona todo. Lo borrado con la goma sigue borrado al mover. |
| **Pegar** | **Ctrl+V** o botón: pega una imagen (o archivo de imagen) centrada en el cursor, lista para moverla o agrandarla; un texto copiado se pega como texto. Se guarda en la sesión y sale en el PDF. |
| **Notas adhesivas** | Tecla **O** o botón de la nota: un clic pega una nota de papel de color (amarilla, rosada, celeste, verde, naranja o blanca) donde se escribe como con Texto; crece con lo escrito. Clic sobre ella para editarla; se mueve, se duplica y se guarda en la sesión y el PDF. |
| **Regla, transportador y compás** | Teclas **I**, **Y** y **Mayús+C** o el botón de la regla. Se mueven arrastrándolos y giran con su botón azul o la rueda. Un trazo que empieza junto a la **regla** sale recto; el **transportador** mide ángulos con su aguja y guía arcos y rectas; el **compás** se abre con la pata del lápiz (radio en cm) y dibuja arcos o circunferencias al girar la punta. No forman parte del dibujo. |
| **Recortar zona** | Tecla **X**, **Ctrl+Alt+R** o el menú de la cámara: la pantalla se congela y se arrastra un rectángulo. Se guarda solo esa parte (con o sin lo dibujado) y se copia al portapapeles, o se **pega en la pizarra** como imagen en el mismo lugar. |
| **Temporizador** | Botón con menú: cuenta regresiva (1 a 30 min u otro tiempo) o cronómetro, en una ventanita siempre encima con pausa, ±1 minuto y aviso «¡Tiempo!» en rojo al terminar. |
| **Color y grosor** | Botón de color con selector completo + paleta de 12 colores; deslizadores de **grosor** y **opacidad** (cada herramienta recuerda su propio tamaño y opacidad). También con la **rueda del ratón** sobre la pizarra. |
| **Texto** | Tecla **T**: clic donde quieras y escribe con el teclado (tildes, ñ, varias líneas, Ctrl+V para pegar). Tamaño de letra, color y **negrita**. Mientras escribes, las teclas no activan atajos. Esc o un clic fuera termina el texto. **Clic sobre un texto ya escrito** (donde todavía se vea: lo borrado con la goma no se reabre) para editarlo: cursor con flechas, Inicio/Fin, Supr, arrastrar para moverlo; cada edición se puede deshacer. |
| **Puntero láser / tinta temporal** | Tecla **L**: el cursor se convierte en un punto luminoso; al arrastrar deja un trazo brillante que **se desvanece solo** (no se guarda). |
| **Fondo** | Transparente, «Oscurecer escritorio», «Pizarra blanca» o «Pizarra verde» (para usarla como pizarra tradicional). |
| **Pautas** | **Cuadrícula**, **papel milimetrado**, **hoja rayada**, **pauta de caligrafía** (4 líneas), **plano cartesiano** con ejes numerados y **pentagrama**, sobre cualquier fondo. Se incluyen en capturas y PDF. En «Ratón libre» la hoja (fondo y pauta) se aparta para poder usar el equipo y vuelve al pasar a «Dibujando». |
| **Foco** | **F** / **Ctrl+Alt+F**: oscurece la pantalla salvo un círculo o un **rectángulo** (franja para leer línea a línea) alrededor del cursor (**Alt + rueda** para su tamaño, **Mayús+F** o clic derecho en el botón para cambiar la forma). Funciona también en «Ratón libre», sobre otros programas. |
| **Cortina** | **V**: tapa la pantalla y se descubre poco a poco **desde arriba, abajo, la izquierda o la derecha** (menú del botón o **Mayús+V** para cambiar de lado), arrastrando su borde o con las **flechas** (preguntas antes que respuestas, textos párrafo a párrafo, tablas columna por columna). |
| **Tapar zona** | Tecla **H**: arrastra para tapar una parte de la pantalla (p. ej. las respuestas) con un rectángulo con «?»; un clic sobre él la descubre. Se puede deshacer y se guarda en la sesión. |
| **Resaltar cursor y clics** | **M** / **Ctrl+Alt+M**: halo amarillo alrededor del puntero y una onda en cada clic (roja izquierdo, azul derecho), también al hacer clic en otros programas. |
| **Mostrar teclas pulsadas** | **Ctrl+Alt+K** o el botón del teclado: los atajos (Ctrl + C, Alt + Tab, Win + D…) y teclas especiales (Intro, Esc, flechas, F1…) que se pulsan en cualquier programa aparecen abajo en el centro; las repeticiones se cuentan (×2). El texto que se escribe nunca se muestra. |
| **Pantalla táctil y modo táctil** | Un dedo dibuja; **dos dedos** (toque) deshacen y **tres** rehacen; con el zoom, **pellizcar** acerca y aleja; la **palma** borra (si la pantalla informa el tamaño del contacto). El **modo táctil** (botón de la mano en la barra) agranda botones, menús y deslizadores; se activa solo si hay pantalla táctil y sirve también sin ella. |
| **Páginas** | Varias páginas por clase, cada una con su dibujo, historial, fondo y pauta. **N** crea una nueva, **AvPág / RePág** pasan de página (compatible con presentadores inalámbricos). |
| **Sesiones y PDF** | **Guardar / abrir** la clase en un archivo `.pizarra` (Ctrl+S / Ctrl+O) y **exportar a PDF** (Ctrl+P) con una página del PDF por página de la pizarra. |
| **Zoom** | **Z**, **Ctrl+Alt+Z** o el botón de la lupa: congela la pantalla donde está el cursor y la amplía (2× al empezar, de 1× a 10×) para hacer énfasis en un detalle. **Rueda** para acercar/alejar centrado en el cursor, **clic derecho (o central) y arrastrar** para moverse, **Esc** para salir. Se puede dibujar encima con cualquier herramienta: los trazos quedan colocados sobre el contenido real al salir del zoom. |
| **Deshacer / rehacer** | Historial ilimitado (también para la goma y «Borrar todo»). |
| **Captura de pantalla** | Con o sin el trazado, de la pantalla actual o de todas, guardada en `%USERPROFILE%\Pictures\Capturas Pizarra` (la carpeta se crea si no existe) y copiada al portapapeles. |
| **Bandeja del sistema** | Icono junto al reloj con menú (modo dibujo, mostrar/ocultar, foco, resaltado, zoom, capturas, sesión y PDF, ayuda, manual, salir). |
| **Manual de usuario** | PDF incluido en el zip y accesible desde el botón de ayuda: todas las funciones, atajos e ideas para clase. Se genera automáticamente desde [`docs/manual.html`](docs/manual.html) con capturas de la versión actual. |

La configuración (herramienta, color, tamaños, posición de la barra…) se recuerda entre sesiones.

## Descargar

En la página de **[Releases](https://github.com/pollorijas/Pizarra_Virtual/releases/latest)** descarga
**`PizarraVirtual-vX.Y.Z.zip`**, descomprímelo y ejecuta `PizarraVirtual.exe`. El zip contiene:

- `PizarraVirtual.exe` — la aplicación (un único archivo, sin instalación).
- `Manual de usuario.pdf` — guía completa de uso.

Los cambios de cada versión están en el **[registro de cambios (CHANGELOG.md)](CHANGELOG.md)**.

Además, cada vez que se sube código a `main`, **GitHub Actions** compila, prueba y empaqueta la versión
en desarrollo: en la pestaña **Actions → «Compilar PizarraVirtual.exe»**, la ejecución más reciente
tiene el artefacto **`PizarraVirtual`** con el mismo `.zip`.

También puedes compilarlo tú mismo: ver [Compilar el .exe](#compilar-el-exe).

## Cómo se usa

1. Ejecuta **`PizarraVirtual.exe`**. Aparece la **barra de herramientas** flotante (a la izquierda) y
   el icono en el área de notificación. La pizarra arranca en modo **Dibujando**.
2. Elige una herramienta, un color y un grosor en la barra y dibuja con el ratón, el lápiz o el dedo.
3. Para volver a usar tus programas sin borrar lo dibujado, pulsa **Ctrl+Alt+D** (o **Esc**, o el
   botón *Dibujando*) → pasa a **Ratón libre**: los dibujos siguen visibles pero los clics atraviesan
   la pizarra. Vuelve a pulsar **Ctrl+Alt+D** para seguir dibujando.
4. **Ctrl+Alt+H** (o el botón del ojo) oculta/muestra todo lo dibujado.
5. La barra se **mueve** arrastrando su título («⠿ Pizarra») y se **pliega** con la flecha ⌃: la
   ventana se reduce a la cabecera y se recuerda plegada para la próxima vez.
6. Para **ampliar** una zona, pon el cursor encima y pulsa **Z** (o **Ctrl+Alt+Z** desde cualquier
   programa). Usa la rueda para el aumento, clic derecho y arrastrar para desplazarte, dibuja lo que
   necesites y sal con **Esc**.
7. Para cerrar la aplicación usa el botón de apagado de la barra, **Alt+F4** o *Salir* en el menú del icono de la
   bandeja.

Barra de herramientas (de arriba abajo): modo dibujo · 10 herramientas · tipo de pincel (solo con el
pincel) · relleno (solo figuras cerradas) · color actual y paleta · grosor · opacidad · fondo ·
deshacer, rehacer, borrar todo · zoom, captura, carpeta de capturas · ocultar, ayuda, salir.

## Atajos de teclado

### Globales (funcionan desde cualquier aplicación, aunque la pizarra no tenga el foco)

| Atajo | Acción |
|---|---|
| **Ctrl+Alt+D** | Activar / desactivar el dibujo (Dibujando ↔ Ratón libre) |
| **Ctrl+Alt+H** | Mostrar / ocultar la pizarra |
| **Ctrl+Alt+Z** | Zoom: ampliar la zona de la pantalla bajo el cursor (y salir del zoom) |
| **Ctrl+Alt+F** | Foco |
| **Ctrl+Alt+M** | Resaltar el cursor y los clics |
| **Ctrl+Alt+K** | Mostrar / ocultar las teclas pulsadas |
| **Ctrl+Alt+R** | Recortar una zona de la pantalla |
| **Ctrl+Alt+S** | Captura de la pantalla actual **con** el trazado |
| **Ctrl+Alt+Shift+S** | Captura de la pantalla actual **sin** el trazado |

### En modo dibujo

| Atajo | Acción |
|---|---|
| **1** | Pincel |
| **2** | Lápiz |
| **3** | Pluma |
| **4** | Destacador |
| **5** | Goma de borrar |
| **6** | Rectángulo / cuadrado |
| **7** | Elipse / círculo |
| **8** | Triángulo |
| **9** | Línea |
| **0** | Flecha |
| **P** | Polígonos: pentágono → hexágono → octágono |
| **D** · **E** · **Q** | Rombo · Estrella · Rectángulo redondeado |
| **J** · **W** · **U** · **K** | Ejes · Flecha doble · Flecha curva · Llave |
| **S** | Sellos (otra vez **S**: siguiente sello) |
| **A** | Seleccionar y mover (Ctrl+A todo · Ctrl+D duplicar · Supr eliminar · Esc quitar selección) |
| **G** | Formas perfectas sí / no |
| **Ctrl+V** | Pegar una imagen o un texto |
| **O** · **H** · **X** | Nota adhesiva · Tapar zona (clic sobre ella: descubrir) · Recortar zona |
| **B** | Cambiar tipo de pincel (Duro → Suave → Aerógrafo → Caligráfico) |
| **T** | Texto |
| **L** | Puntero láser / tinta temporal |
| **R** | Activar / desactivar relleno de figuras |
| **C** | Abrir el selector de color |
| **+** / **-** (o **]** / **[**) | Aumentar / reducir el grosor |
| **Rueda del ratón** | Aumentar / reducir el grosor |
| **Mayús + rueda** | Aumentar / reducir la opacidad |
| **Mayús** mientras se arrastra | Cuadrado, círculo, triángulo proporcionado o ángulos de 15° |
| **Clic derecho** | Cancelar el trazo o la figura en curso |
| **Ctrl+Z** | Deshacer |
| **Ctrl+Y** o **Ctrl+Shift+Z** | Rehacer |
| **Supr** | Borrar todo (se puede deshacer); con algo seleccionado, solo eso |
| **Z** | Activar / salir del zoom |
| **F** · **V** · **M** | Foco · Cortina · Resaltar cursor y clics |
| **Mayús+F** | Foco en círculo o en rectángulo |
| **Mayús+V** | Cortina desde el lado siguiente (arriba → abajo → izquierda → derecha) |
| **Flechas** | Mover el borde de la cortina (↓ con la de arriba descubre, ↑ vuelve a tapar…) |
| **Alt + rueda** | Tamaño del foco |
| **N** | Página nueva |
| **AvPág / RePág** | Página siguiente / anterior |
| **Ctrl+S** · **Ctrl+Shift+S** | Guardar sesión · Guardar como |
| **Ctrl+O** · **Ctrl+P** | Abrir sesión · Exportar a PDF |
| **Esc** | Cancelar el recorte o salir del zoom; si no, quitar la selección o pasar a «Ratón libre» |
| **F1** | Ayuda con la lista de atajos |

### En el zoom

| Atajo | Acción |
|---|---|
| **Rueda del ratón** | Acercar / alejar (el punto bajo el cursor se queda fijo) |
| **Clic derecho o central + arrastrar** | Mover la vista |
| **Ctrl + rueda** | Grosor de la herramienta |
| **Mayús + rueda** | Opacidad |
| **Esc**, **Z** o **Ctrl+Alt+Z** | Salir del zoom |

### Escribiendo texto

| Atajo | Acción |
|---|---|
| **Intro** | Nueva línea |
| **Esc**, **Ctrl+Intro** o clic fuera | Terminar el texto |
| **Retroceso** · **Ctrl+V** · **Tab** | Borrar · Pegar · Sangría |

El zoom muestra una imagen congelada de la pantalla (los vídeos o animaciones no se mueven mientras
dura); al salir se vuelve a ver el escritorio en vivo con lo dibujado encima.

> Si otro programa ya usa alguno de los atajos globales, Pizarra Virtual lo avisa al arrancar; el resto
> de atajos y todos los botones siguen funcionando.

## Capturas de pantalla

Botón de la cámara (o los atajos globales) → opciones:

- **Pantalla actual con trazado** (`Ctrl+Alt+S`)
- **Pantalla actual sin trazado** (`Ctrl+Alt+Shift+S`)
- **Todas las pantallas con trazado**
- **Todas las pantallas sin trazado**

La «pantalla actual» es la del monitor donde está el cursor. Antes de capturar, la barra y la pizarra
se ocultan un instante para que no aparezcan en la imagen; en las capturas «con trazado» el dibujo se
compone encima a resolución nativa. Si se captura **durante el zoom**, se guarda exactamente la
vista ampliada que se está mostrando.

Las imágenes se guardan en PNG en:

```
%USERPROFILE%\Pictures\Capturas Pizarra\Pizarra_AAAA-MM-DD_HH-MM-SS.png
```

(es decir, la carpeta **Imágenes › Capturas Pizarra** del usuario; se crea si no existe). Además la
captura se copia al portapapeles y se muestra una notificación; al hacer clic en ella se abre la
carpeta.

## Compilar el .exe

### Opción A: script automático (Windows)

Requisitos: **Python 3.10–3.13 de 64 bits** para Windows (marca *Add python.exe to PATH* al instalar).

```bat
build.bat
```

El script crea un entorno virtual `.venv`, instala las dependencias, genera
**`dist\PizarraVirtual.exe`**, el **`dist\Manual de usuario.pdf`** y el paquete
**`dist\PizarraVirtual.zip`** con ambos.

### Opción B: paso a paso (PowerShell o CMD)

```bat
py -3 -m venv .venv
```

```bat
.venv\Scripts\activate
```

```bat
pip install -r requirements.txt -r requirements-dev.txt
```

```bat
pyinstaller --noconfirm --clean PizarraVirtual.spec
```

El resultado es un único archivo, `dist\PizarraVirtual.exe` (sin consola, con icono y metadatos de
versión). Para comprobar que el ejecutable funciona sin abrir la interfaz:

```bat
dist\PizarraVirtual.exe --selftest
```

(devuelve código 0 si todo está bien y deja el detalle en `%LOCALAPPDATA%\PizarraVirtual\pizarra.log`).

### Opción C: GitHub Actions

El flujo [`.github/workflows/build.yml`](.github/workflows/build.yml) hace lo mismo en `windows-latest`
en cada push a `main`, en cada pull request y bajo demanda (*Run workflow*). Para publicar una
versión, primero:

1. sube el número en `pizarra_virtual/__init__.py` y `version_info.txt`;
2. añade su sección `## [X.Y.Z] - fecha` al principio de [`CHANGELOG.md`](CHANGELOG.md) (registro de
   cambios de todas las versiones);
3. escribe sus notas en `notas/vX.Y.Z.md` (texto de la release; ver
   [`notas/v1.4.0.md`](notas/v1.4.0.md)).

El flujo comprueba esos tres puntos y no publica si falta alguno. Súbelos y después crea y sube la
etiqueta:

```bash
git tag v1.4.0
```

```bash
git push origin v1.4.0
```

También se puede publicar sin crear la etiqueta a mano: en **Actions → Compilar PizarraVirtual.exe →
Run workflow**, escribe la versión (p. ej. `v1.4.0`) en el campo *version* (y marca *borrar_anteriores* para dejar solo esa); el flujo crea la etiqueta
sobre ese commit. En ambos casos vuelve a pasar todas las pruebas y, solo si todo va bien, publica la
release con el `.zip` (ejecutable + manual).

> PyInstaller no compila de forma cruzada: el `.exe` de Windows debe generarse en Windows (en tu PC o
> en el runner de GitHub Actions).

### Manual de usuario

El manual se escribe en [`docs/manual.html`](docs/manual.html) y se convierte a PDF con capturas
generadas automáticamente de la versión actual:

```bat
python tools\build_manual.py --out "dist\Manual de usuario.pdf"
```

### Regenerar el icono (opcional)

`assets/pizarra.ico` se genera a partir del icono vectorial de la aplicación:

```bat
python tools\make_icon.py
```

## Ejecutar desde el código fuente y pruebas

```bat
pip install -r requirements.txt
```

```bat
python main.py
```

Pruebas automáticas (rasterizado de todas las herramientas, deshacer/rehacer, goma, figuras, pluma
—suavizado, afinado, velocidad, contorno sin huecos—, zoom, barra plegable, modo ratón libre, capturas
y ajustes) con Qt en modo `offscreen`:

```bat
pip install -r requirements-dev.txt
```

```bat
python -m pytest -q
```

(`tests/conftest.py` activa automáticamente `QT_QPA_PLATFORM=offscreen`, así que no se abre ninguna ventana).

`tests/test_windows_native.py` contiene pruebas que solo se ejecutan en Windows con ventanas reales
(`QT_QPA_PLATFORM=windows`): tamaño real de la barra al plegarla, estilos que dejan pasar los clics,
atajos globales y capturas del escritorio que comprueban que el trazo y el zoom se ven de verdad.
GitHub Actions las ejecuta a 100 % y a 150 % de escala en cada compilación.

## Stack tecnológico y justificación

**Python 3.12 + PySide6 (Qt 6.8 LTS) + PyInstaller.**

- **Qt resuelve lo difícil de una superposición en Windows**: ventanas sin bordes, siempre encima,
  con transparencia por píxel (*layered windows*) y que dejan pasar los clics
  (`WindowTransparentForInput` → `WS_EX_TRANSPARENT`), sin tener que escribir todo a mano con Win32.
- **Soporte de DPI moderno**: Qt 6 declara la aplicación *Per-Monitor DPI Aware v2*, así que cada
  monitor se dibuja a su resolución física aunque tengan escalados distintos.
- **Entrada de tableta con presión** (`QTabletEvent`, Windows Ink / WM_POINTER) lista para usar: es lo
  que permite que la pluma use la presión real cuando hay tableta.
- **QPainter** ofrece antialiasing, degradados radiales (pincel suave), modos de composición (goma) y
  opacidad por capa (destacador sin acumulación), suficiente para un editor sencillo y rápido.
- **PySide6 es la binding oficial de Qt** (licencia LGPL, compatible con la GPL del proyecto) y
  **Qt 6.8 es LTS** con soporte oficial para **Windows 10 (1809+) y Windows 11**.
- **PyInstaller** es la herramienta estándar para empaquetar apps Python en un único `.exe` sin
  dependencias para el usuario final, y se integra fácilmente en GitHub Actions.
- Python permite además probar toda la lógica de dibujo de forma automática (Qt *offscreen*).

Se consideró **C# + WPF**, igualmente válido, pero WPF no trae entrada de presión de tableta tan
directa como `QTabletEvent` y la transparencia por píxel con clics que atraviesan requiere más
interoperabilidad Win32; con Qt el resultado es equivalente con menos código específico.

Lo único que se hace con `ctypes` contra la API de Windows es: atajos globales (`RegisterHotKey`), el
identificador de aplicación para la barra de tareas y un refuerzo del estilo *click-through*.

## Compatibilidad: Windows 10/11, DPI y varios monitores

- **Una superposición por monitor**: cada pantalla tiene su propia ventana transparente con un lienzo
  a la resolución física de ese monitor (p. ej. 3840×2160 a 150 %), así que los trazos se ven nítidos
  incluso con escalados distintos entre monitores. La barra de herramientas puede moverse a cualquier
  monitor.
- Los trazos se guardan como **vectores** (puntos, grosores, colores), por lo que si cambias la
  escala o la resolución de Windows con la app abierta, el lienzo se vuelve a renderizar a la nueva
  resolución sin perder calidad.
- **Conexión y desconexión de monitores** en caliente: se crean o eliminan las superposiciones
  automáticamente.
- **Barra adaptable**: si la barra no cabe a lo alto de la pantalla (por ejemplo, un portátil de
  1366×768 con escalado al 125–150 %), se coloca automáticamente en **dos columnas**; al llevarla a
  otro monitor se vuelve a calcular. Su cabecera nunca queda fuera de la pantalla.
- El factor de escala no se redondea (`PassThrough`), para que 125 %, 150 % o 175 % coincidan píxel a
  píxel con la pantalla.
- Las capturas usan los píxeles físicos de cada monitor; «Todas las pantallas» las une en una sola
  imagen según la disposición configurada en Windows.

## Estructura del proyecto

```
Pizarra_Virtual/
├── main.py                       # Lanzador (punto de entrada de PyInstaller)
├── PizarraVirtual.spec           # Configuración de PyInstaller (.exe de un solo archivo, sin consola)
├── version_info.txt              # Metadatos de versión del .exe
├── build.bat                     # Compilación con un clic en Windows
├── requirements.txt              # Dependencias de ejecución (PySide6-Essentials)
├── requirements-dev.txt          # PyInstaller, pytest, Pillow
├── assets/                       # Icono (.ico y .png)
├── tools/make_icon.py            # Genera assets/pizarra.ico
├── tools/build_manual.py         # Genera «Manual de usuario.pdf» desde docs/manual.html
├── docs/manual.html              # Texto del manual de usuario
├── notas/                        # Notas de cada versión publicada (texto de la release)
├── CHANGELOG.md                  # Registro de cambios de todas las versiones
├── pizarra_virtual/
│   ├── main.py                   # Arranque: DPI, instancia única, registro de errores
│   ├── app.py                    # Controlador: estado, páginas, modos, efectos, sesiones, capturas, atajos
│   ├── overlay.py                # Superposición por monitor: ratón, tableta, toques y lienzo
│   ├── render.py                 # Rasterizado de pinceles, pluma, texto, figuras, sellos y pautas
│   ├── templates.py              # Plantillas (mapa conceptual, línea de tiempo, Venn, tablas…)
│   ├── shape_recognition.py      # «Formas perfectas»: reconocimiento de formas dibujadas a mano
│   ├── timer.py                  # Temporizador / cronómetro en pantalla
│   ├── keyview.py                # «Mostrar teclas pulsadas» (solo atajos, nunca el texto)
│   ├── instruments.py            # Regla, transportador y compás
│   ├── session.py                # Páginas, sesiones .pizarra y exportación a PDF
│   ├── toolbar.py                # Barra de herramientas flotante
│   ├── hotkeys.py                # Atajos globales (RegisterHotKey)
│   ├── capture.py                # Captura de pantalla y carpeta «Capturas Pizarra»
│   ├── icons.py                  # Iconos vectoriales
│   ├── tools.py / items.py       # Definición de herramientas y del modelo de trazos
│   ├── winutil.py                # Utilidades Win32 (ctypes)
│   └── selftest.py               # Autodiagnóstico (--selftest)
├── tests/                        # Pruebas automáticas (pytest)
└── .github/workflows/build.yml   # Compilación del .exe en GitHub Actions
```

## Solución de problemas

- **Windows SmartScreen muestra «Windows protegió su PC»**: el `.exe` no está firmado digitalmente.
  Pulsa *Más información → Ejecutar de todas formas*.
- **El antivirus marca el .exe**: algunos antivirus desconfían de los ejecutables de PyInstaller de un
  solo archivo (falso positivo). Puedes compilarlo tú mismo con `build.bat`.
- **Arranca un poco lento la primera vez**: el `.exe` de un solo archivo se descomprime en una
  carpeta temporal al iniciarse; es normal que tarde 1–3 segundos.
- **Un atajo global no funciona**: otra aplicación lo tiene registrado (la app avisa al arrancar).
  Usa el botón equivalente de la barra o del icono de la bandeja.
- **No puedo hacer clic en mis programas**: estás en modo **Dibujando** (o en el zoom). Pulsa
  **Ctrl+Alt+D** o **Esc** para pasar a **Ratón libre**.
- **Registro de errores**: `%LOCALAPPDATA%\PizarraVirtual\pizarra.log`.

## Licencia

Distribuido bajo la licencia **GNU GPL v2** (ver [LICENSE](LICENSE)). Usa Qt for Python (PySide6) bajo
licencia LGPL v3.
