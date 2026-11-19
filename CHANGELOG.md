# Registro de cambios

Todos los cambios importantes de **Pizarra Virtual**, de la versión más reciente a la más antigua.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones
siguen [Versionado Semántico](https://semver.org/lang/es/): `MAYOR.MENOR.PARCHE`, donde
**PARCHE** son correcciones, **MENOR** son funciones nuevas compatibles y **MAYOR** son cambios
incompatibles.

Cada versión publicada debe tener su sección aquí: el flujo de publicación de GitHub Actions se
detiene si falta.

## [1.3.0] - 2026-11-19

### Añadido
- **Plantillas** (botón «Plantillas»): mapa conceptual, línea de tiempo, diagramas de Venn de 2 y 3
  conjuntos, tabla de dos columnas, tabla S-Q-A (sé / quiero saber / aprendí), esquema de redacción,
  ciclo de 4 etapas y causa y efecto. Se insertan centradas en la pantalla con el color actual, se
  quitan de una vez con Ctrl+Z y cada rótulo se edita con un clic (la herramienta Texto queda activa).
- **Sellos** (tecla S o botón «Sellos»): ✔ correcto, ✘ incorrecto, estrella, carita feliz, números
  (1, 2, 3… que siguen la cuenta en la página y retroceden al deshacer) e interrogación. Un clic
  pone el sello y el cursor muestra una vista previa.
- **Más figuras** (botón «Más figuras»): pentágono, hexágono y octágono (P), rombo (D), estrella (E),
  rectángulo redondeado (Q), ejes de coordenadas (J), flecha doble (W), flecha curva (U) y llave (K).
  Las cerradas se pueden rellenar.

### Corregido
- **Un texto borrado con la goma se podía volver a abrir.** Al hacer clic donde había estado, el texto
  invisible se abría para editarlo. Ahora un texto solo se abre donde todavía se ve su tinta: si se
  borró con la goma o con «Borrar todo», el clic empieza un texto nuevo; si se borró a medias, se abre
  desde la parte visible y lo borrado sigue borrado mientras se edita.

### Cambiado
- La barra de herramientas tiene una fila más con los botones «Más figuras», «Sellos» y «Plantillas».
- Las sesiones `.pizarra` guardan sellos y plantillas; las de versiones anteriores se abren igual.

## [1.2.2] - 2026-11-18

### Añadido
- **Editar textos ya escritos.** Con la herramienta Texto, un clic sobre un texto lo abre de nuevo:
  el cursor de escritura se coloca donde se hizo clic y se mueve con ← → ↑ ↓, Inicio / Fin y
  Ctrl+Inicio / Ctrl+Fin; Supr borra hacia delante; arrastrar el texto lo cambia de lugar; la barra
  muestra su color, tamaño y negrita para cambiarlos. Borrar todas sus letras elimina el texto y el
  clic derecho descarta los cambios. Cada edición se puede deshacer y se guarda en la sesión.
- **Foco rectangular**: además del círculo, una franja ancha y baja para leer un texto línea a línea.
  Se cambia con **Mayús+F**, con clic derecho sobre el botón del foco o desde el menú del icono
  junto al reloj, y el programa recuerda la forma elegida.
- **Papel milimetrado** como nueva pauta, con líneas finas, intermedias cada 5 y marcadas cada 10.

### Cambiado
- Mientras se escribe un texto, un marco discontinuo indica cuál es; la opacidad también se aplica
  al texto en curso.
- Las sesiones `.pizarra` guardan un identificador por texto (necesario para las ediciones). Las
  sesiones de versiones anteriores se siguen abriendo sin cambios.

## [1.2.1] - 2026-11-18

### Corregido
- **Alt+F4 dejaba la hoja de fondo fija en el escritorio.** Alt+F4 cerraba solo la barra de
  herramientas; la pizarra seguía abierta y siempre encima, y con una pizarra blanca o una pauta
  (cuadrícula, plano cartesiano…) tapaba la pantalla, también en otros escritorios virtuales, sin
  forma de quitarla. Ahora cerrar cualquier ventana del programa lo cierra entero (preguntando si
  hay cambios sin guardar), también mientras se escribe un texto.
- **«Ratón libre» con una hoja de fondo dejaba la pantalla bloqueada.** La hoja seguía tapando el
  escritorio y la barra podía quedar debajo de ella, sin forma de volver a la aplicación. Ahora en
  «Ratón libre» la hoja (fondo y pauta) se aparta y solo quedan los trazos; vuelve igual al pasar a
  «Dibujando». La barra se mantiene siempre por encima al cambiar de modo.
- **Manual de usuario sin letras.** El PDF se generaba sin fuentes y cada letra salía como un
  cuadrado negro (y los rótulos de las imágenes como cuadrados blancos). Ahora usa Segoe UI, y la
  compilación comprueba que el PDF tiene texto legible.

### Cambiado
- Las capturas hechas en «Ratón libre» guardan lo que realmente se ve (sin la hoja de fondo).
- El manual y el README indican Alt+F4 como forma de salir y explican qué pasa con la hoja en
  «Ratón libre».

## [1.2.0] - 2026-11-18

### Añadido
- **Texto** (T): escribir con el teclado en cualquier lugar, con tildes y ñ, varias líneas, tamaño,
  color y negrita. Mientras se escribe, las teclas no activan atajos.
- **Puntero láser con tinta temporal** (L).
- **Foco** (F · Ctrl+Alt+F): oscurece la pantalla menos un círculo alrededor del cursor.
- **Cortina** (V): tapa la pantalla y se descubre poco a poco.
- **Resaltar cursor y clics** (M · Ctrl+Alt+M), también sobre otros programas.
- **Pautas**: cuadrícula, hoja rayada, pauta de caligrafía, plano cartesiano y pentagrama.
- **Páginas** (N, AvPág / RePág), cada una con su dibujo, historial, fondo y pauta.
- **Guardar y abrir sesiones** `.pizarra` (Ctrl+S / Ctrl+O) y **exportar a PDF** (Ctrl+P).
- **Manual de usuario** en PDF, incluido en el `.zip` y accesible desde el botón de ayuda.

### Cambiado
- El relleno de figuras pasa de la tecla F a la **R** (F es ahora el foco).
- La descarga es un `.zip` con el ejecutable y el manual.

## [1.1.0] - 2026-11-18

### Añadido
- **Zoom de pantalla** (Z · Ctrl+Alt+Z) de 1× a 10×, con dibujo encima.
- Barra de herramientas en **dos columnas** cuando no cabe en la altura de la pantalla.

### Cambiado
- **Pluma más precisa**: curva suave, estabilizador, grosor según velocidad o presión real.

### Corregido
- El botón de plegar reducía solo el contenido de la barra y no la ventana.

## [1.0.0] - 2026-11-13

### Añadido
- Primera versión: pizarra transparente sobre el escritorio de Windows 10 y 11, con pincel (varios
  tipos), lápiz, pluma, marcador, goma, figuras (rectángulo, elipse, triángulo, línea, flecha),
  colores, grosor y opacidad, deshacer/rehacer, capturas con y sin dibujo, atajos globales, modo
  «Ratón libre», varios monitores y escalado de pantalla (DPI).

[1.3.0]: https://github.com/pollorijas/Pizarra_Virtual/releases/tag/v1.3.0
[1.2.2]: https://github.com/pollorijas/Pizarra_Virtual/releases/tag/v1.2.2
[1.2.1]: https://github.com/pollorijas/Pizarra_Virtual/releases/tag/v1.2.1
