# Registro de cambios

Todos los cambios importantes de **Pizarra Virtual**, de la versión más reciente a la más antigua.
El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones
siguen [Versionado Semántico](https://semver.org/lang/es/): `MAYOR.MENOR.PARCHE`, donde
**PARCHE** son correcciones, **MENOR** son funciones nuevas compatibles y **MAYOR** son cambios
incompatibles.

Cada versión publicada debe tener su sección aquí: el flujo de publicación de GitHub Actions se
detiene si falta.

## [Sin publicar]

### Añadido
- **Regla, transportador y compás** (botón de la regla en la barra, teclas **I**, **Y** y
  **Mayús+C**). Se colocan encima de la pizarra, se mueven arrastrándolos, giran con su botón azul o
  con la rueda del ratón (los ángulos de 15° atraen; con Mayús el giro es libre) y se quitan con su
  botón rojo. No forman parte del dibujo ni del historial.
  - **Regla** con escala en centímetros reales de la pantalla: un trazo que empieza junto a uno de
    sus bordes sale recto, pegado al borde.
  - **Transportador** de 180° con aguja para medir ángulos (el número grande indica los grados),
    tamaño ajustable; los trazos junto al arco siguen el arco y junto a la base salen rectos.
  - **Compás**: se abre con la pata del lápiz (indica el radio en cm) y dibuja arcos o
    circunferencias completas al girar la punta del lápiz, con el color y el grosor actuales.

### Cambiado
- La barra hace sitio al nuevo botón: **Pegar** pasa al grupo de acciones (junto a la captura) y el
  desplegable del fondo ya no lleva el rótulo «Fondo» (lo explica su descripción emergente).
- La barra mide su altura con las opciones de la herramienta que más ocupa (el pincel), no con
  todas a la vez, para decidir si va en una o dos columnas.
- Simplificación interna del borrado con la palma, de la cancelación del recorte y de la lectura del
  tamaño de los toques (sin cambios de comportamiento).

## [1.5.1] - 2026-11-19

### Corregido
- **Modo táctil al primer inicio**: se activaba solo en equipos con una tableta de lápiz (por
  ejemplo, Wacom) aunque no tuvieran pantalla táctil, porque se consultaba un dato equivocado de
  Windows. Ahora solo se activa si hay una pantalla táctil de verdad.
- **Tamaño de la goma tras usar la palma**: si un segundo dedo tocaba la pantalla justo después de
  apoyar la palma (o Windows cancelaba el toque), la goma quedaba con el tamaño de la palma (hasta
  250 px) y se guardaba así. Ahora siempre vuelve a su tamaño al terminar el toque.
- **Recortar zona y «Ratón libre»**: si se pasaba a «Ratón libre» (Ctrl+Alt+D) o se ocultaba la
  pizarra (Ctrl+Alt+H) en medio de un recorte, la pantalla congelada seguía encima mientras los
  clics llegaban a los programas de debajo. Ahora el recorte se cancela.
- **Apoyar la mano al escribir con el dedo**: si el canto de la mano tocaba la pantalla poco
  después de empezar a escribir, el trazo podía convertirse en goma. Ahora el tamaño del contacto
  se mira por cada toque y solo cuenta cuando hay uno solo.
- **Clics ignorados después de un toque**: durante un segundo después de usar el dedo se ignoraban
  los clics simulados por Windows; ahora solo el que corresponde a ese mismo toque.
- **Mostrar teclas**: al activarlo con Ctrl+Alt+K ya no aparece en pantalla su propio atajo.
- **Modo táctil**: al activarlo o desactivarlo, durante un instante un atajo de teclado podía
  ejecutarse dos veces (en la barra anterior y en la nueva).

## [1.5.0] - 2026-11-19

### Añadido
- **Cortina desde cualquier lado**: además de bajar desde arriba, ahora se descubre desde abajo,
  desde la izquierda o desde la derecha.
  - El botón de la cortina abre un menú con los cuatro lados y la opción de quitarla.
  - **V** pone o quita la cortina (recuerda el último lado) y **Mayús+V** pasa al lado siguiente.
  - Se descubre arrastrando su borde o con las flechas en su dirección (↓ con la de arriba,
    → con la de la izquierda…); la flecha contraria vuelve a tapar.
- **Tapar zona** (tecla **H**, botón en «Presentación»): arrastrar tapa una parte de la pantalla
  con un rectángulo oscuro con «?», por ejemplo las respuestas de un ejercicio. Un clic sobre él
  la descubre. Se puede deshacer, mover con Seleccionar, y se guarda en la sesión.
- **Notas adhesivas** (tecla **O**, botón de la nota): un clic pega una nota de papel de color
  donde se escribe como con Texto; crece con lo escrito.
  - Seis colores de papel (amarilla, rosada, celeste, verde, naranja y blanca) en el menú del botón.
  - Un clic sobre una nota la vuelve a abrir para editarla; se mueve, se duplica y se guarda en la
    sesión y en el PDF.
- **Recortar zona** (tecla **X**, **Ctrl+Alt+R** desde cualquier aplicación, o el menú de la
  cámara): la pantalla se congela y se arrastra un rectángulo.
  - Se guarda solo esa parte en la carpeta de capturas y se copia al portapapeles, con o sin lo
    dibujado.
  - «Recortar zona y pegarla en la pizarra» la deja como imagen en el mismo lugar, lista para
    moverla o agrandarla.
  - Con el zoom activo se recorta la vista ampliada. Esc o clic derecho cancelan.
- **Mostrar teclas pulsadas** (botón del teclado en «Presentación», **Ctrl+Alt+K**): los atajos
  que se pulsan en cualquier programa (Ctrl + C, Alt + Tab, Win + D…) y las teclas especiales
  (Intro, Esc, Tab, flechas, F1…F12, Supr) aparecen abajo en el centro de la pantalla y se
  desvanecen. Si se repiten, muestran «×2», «×3». Por privacidad, el texto que se escribe nunca se
  muestra.
- **Pantalla táctil**:
  - Un dedo dibuja; un toque con **dos dedos** deshace y uno con **tres dedos** rehace.
  - Con el zoom activo, pellizcar acerca o aleja y mueve la vista.
  - Si la pantalla informa el tamaño del contacto, apoyar la **palma** borra.
- **Modo táctil** (botón de la mano en la cabecera de la barra, o el menú de la bandeja): botones,
  letras, menús y deslizadores más grandes, y zonas de agarre más anchas. Sirve también en
  pantallas sin tacto, por ejemplo un proyector manejado de lejos. Se activa solo la primera vez
  si Windows detecta una pantalla táctil, y se recuerda.

### Cambiado
- El temporizador pasa a la sección «Presentación» de la barra.
- Las flechas ← → también mueven la cortina cuando se descubre desde un lado.

### Corregido
- **Ratón simulado al usar el dedo**: al levantar el dedo, Windows enviaba además un clic de ratón
  «simulado» que dejaba un punto suelto con la herramienta activa (por ejemplo, después de borrar
  con la palma). Ahora ese clic se ignora.
- **Borrar con la palma en Windows**: Qt no entrega en Windows el tamaño del contacto de los toques.
  El programa lo lee directamente del sistema; si Windows lo informa un instante después de empezar,
  el trazo se convierte en goma desde el inicio.
- **Gesto de dos dedos con la goma**: si el primer dedo llegaba a borrar algo antes de apoyar el
  segundo, eso quedaba borrado aunque el gesto era «deshacer». Ahora se descarta.
- **Barra en pantallas bajas**: con los botones nuevos, la barra en dos columnas no cabía por pocos
  píxeles en una pantalla de 1366×768 al 150 %; se compactó el espacio entre secciones.

## [1.4.0] - 2026-11-19

### Añadido
- **Seleccionar y mover** (tecla A o botón de la flecha con recuadro):
  - Selección: un clic sobre un trazo, figura, texto, sello o imagen lo selecciona; arrastrar en un
    espacio vacío dibuja un lazo; Ctrl+A selecciona todo lo visible.
  - Mover y cambiar de tamaño: arrastrar la selección la mueve (con Mayús, solo en horizontal o
    vertical) y el asa de la esquina cambia su tamaño.
  - Atajos: Supr elimina lo seleccionado, Ctrl+D lo duplica y Esc quita la selección.
  - Lo movido queda delante y conserva las partes borradas con la goma. Todo se puede deshacer y
    se guarda en la sesión.
- **Pegar imágenes y textos** (Ctrl+V o botón «Pegar»):
  - Una imagen copiada, o un archivo de imagen copiado en el Explorador, aparece centrada en el
    cursor, con un tamaño máximo de media pantalla, y queda seleccionada para moverla o
    agrandarla. Se guarda en la sesión y sale en el PDF.
  - Un texto copiado se pega como texto.
- **Formas perfectas** (reconocimiento de formas): opción que se activa o desactiva con el botón
  «Formas perfectas» (con pincel, lápiz o pluma) o la tecla G. Viene **desactivada**. Al soltar el
  trazo, las rectas, círculos, elipses, rectángulos, triángulos y polígonos de hasta seis lados
  dibujados a mano se convierten en figuras exactas; lo demás queda tal cual.
- **Temporizador** (botón del cronómetro): cuenta regresiva de 1 a 30 minutos, otro tiempo o
  cronómetro.
  - Una ventanita siempre encima, que se puede arrastrar, con pausa, ±1 minuto, volver a empezar
    y una barra de progreso.
  - Al terminar se pone en rojo con «¡Tiempo!» y suena un aviso.
  - No aparece en las capturas ni dentro del zoom.

### Cambiado
- Supr borra solo lo seleccionado cuando hay una selección; si no, borra la página como antes.
- Esc quita primero la selección y, después, pasa a «Ratón libre» como antes.
- Las sesiones `.pizarra` guardan un identificador por elemento, las imágenes y los pasos de
  mover, duplicar y eliminar. Las sesiones de versiones anteriores se siguen abriendo.
- El flujo de compilación usa las versiones actuales de las acciones de GitHub (Node 24).

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

[1.4.0]: https://github.com/pollorijas/Pizarra_Virtual/releases/tag/v1.4.0
[1.3.0]: https://github.com/pollorijas/Pizarra_Virtual/releases/tag/v1.3.0
[1.2.2]: https://github.com/pollorijas/Pizarra_Virtual/releases/tag/v1.2.2
[1.2.1]: https://github.com/pollorijas/Pizarra_Virtual/releases/tag/v1.2.1
