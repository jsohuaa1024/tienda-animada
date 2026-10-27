import asyncio
import base64
import json
import math
import os
import ssl
import tempfile
import uuid
import zlib

# Parche para evitar errores de certificados SSL al descargar imágenes de prueba
ssl._create_default_https_context = ssl._create_unverified_context

import flet as ft

# Datos iniciales compartidos de la tienda
productos = [
    {"id": 1, "name": "Camisa Casual", "price": 25.0, "image": "https://picsum.photos/200/200?random=1"},
    {"id": 2, "name": "Zapatillas Urbanas", "price": 60.0, "image": "https://picsum.photos/200/200?random=2"},
    {"id": 3, "name": "Mochila Exec", "price": 45.0, "image": "https://picsum.photos/200/200?random=3"},
]

carrito = []


# ---------------------------------------------------------------------------
# Transferencia de productos entre dispositivos (código de texto / QR)
# ---------------------------------------------------------------------------
PREFIJO = "TIENDA1:"
PICSUM = "https://picsum.photos/200/200?random="


def codificar_productos(lista):
    """Convierte los productos en un texto compacto (JSON -> zlib -> base64)."""
    items = []
    for p in lista:
        img = p["image"]
        if img.startswith(PICSUM) and img[len(PICSUM):].isdigit():
            img_c = int(img[len(PICSUM):])      # solo guardamos la semilla
        elif img.startswith(("http://", "https://")):
            img_c = img                         # URL externa
        else:
            img_c = None                        # archivo local: no se puede transferir
        items.append([p["name"], p["price"], img_c])
    crudo = json.dumps(items, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return PREFIJO + base64.urlsafe_b64encode(zlib.compress(crudo, 9)).decode("ascii")


def decodificar_productos(texto):
    """Inverso de codificar_productos. Lanza ValueError si el código no es válido."""
    texto = "".join((texto or "").split())      # quita espacios y saltos de línea
    if not texto.startswith(PREFIJO):
        raise ValueError("Ese código no pertenece a esta tienda.")
    try:
        crudo = zlib.decompress(base64.urlsafe_b64decode(texto[len(PREFIJO):]))
        items = json.loads(crudo.decode("utf-8"))
        nuevos = []
        for nombre, precio, img in items:
            nombre = str(nombre).strip()[:60]
            precio = float(precio)
            if not nombre or not math.isfinite(precio) or precio < 0:
                continue
            if isinstance(img, int) and not isinstance(img, bool):
                img = f"{PICSUM}{img}"
            elif not (isinstance(img, str) and img.startswith(("http://", "https://"))):
                img = None
            nuevos.append({"name": nombre, "price": precio, "image": img})
    except Exception:
        raise ValueError("El código está dañado o incompleto.") from None
    if not nuevos:
        raise ValueError("El código no contiene productos válidos.")
    return nuevos


def importar_productos(nuevos):
    """Agrega los productos nuevos; si el nombre ya existe, actualiza su precio."""
    agregados = actualizados = 0
    for n in nuevos:
        existente = next((p for p in productos if p["name"].lower() == n["name"].lower()), None)
        if existente:
            existente["price"] = n["price"]
            actualizados += 1
        else:
            nuevo_id = max((p["id"] for p in productos), default=0) + 1
            productos.append({
                "id": nuevo_id,
                "name": n["name"],
                "price": n["price"],
                "image": n["image"] or f"{PICSUM}{nuevo_id}",
            })
            agregados += 1
    return agregados, actualizados


def generar_qr_png(texto):
    """Genera el QR como PNG en la carpeta temporal y devuelve la ruta. Requiere 'segno'."""
    import segno
    qr = segno.make(texto, error="l", micro=False)
    ruta = os.path.join(tempfile.gettempdir(), f"tienda_qr_{uuid.uuid4().hex}.png")
    qr.save(ruta, scale=6, border=2)
    return ruta


def leer_qr_desde_imagen(ruta):
    """Lee un QR desde un archivo de imagen. Requiere 'opencv-python'."""
    import cv2
    import numpy as np
    img = cv2.imdecode(np.fromfile(ruta, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    detector = cv2.QRCodeDetector()
    texto, _, _ = detector.detectAndDecode(img)
    if not texto:
        grande = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        texto, _, _ = detector.detectAndDecode(grande)
    return texto or None


def escanear_qr_camara():
    """Abre la cámara en una ventana aparte hasta leer un QR (Q o Esc para cancelar).
    Requiere 'opencv-python'. Devuelve el texto leído o None si se canceló."""
    import cv2
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("No se pudo abrir la cámara.")
    detector = cv2.QRCodeDetector()
    ventana = "Escanear QR - pulsa Q para cancelar"
    resultado = None
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            texto, _, _ = detector.detectAndDecode(frame)
            if texto:
                resultado = texto
                break
            cv2.imshow(ventana, frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
            if cv2.getWindowProperty(ventana, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return resultado


def boton(texto, icono, color_fondo, on_click, radio=10):
    """Botón con estilo (Flet 1.0: Button + ButtonStyle)."""
    return ft.Button(
        content=texto,
        icon=icono,
        on_click=on_click,
        style=ft.ButtonStyle(
            color=ft.Colors.WHITE,
            bgcolor=color_fondo,
            shape=ft.RoundedRectangleBorder(radius=radio),
        ),
    )


def parse_precio(texto):
    """Convierte '12,5' o '12.5' en float. Lanza ValueError si no es válido."""
    precio = float(str(texto).strip().replace(",", "."))
    if precio < 0:
        raise ValueError("precio negativo")
    return precio


def main(page: ft.Page):
    page.title = "Tienda Animada - Admin & Usuario"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    es_movil = page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS)
    if not es_movil:
        page.window.width = 450
        page.window.height = 800
        page.window.resizable = False
    page.bgcolor = ft.Colors.SURFACE_CONTAINER_HIGHEST

    # En Flet 1.0 el FilePicker es un "servicio", no va en overlay
    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    def notify(msg: str):
        page.show_dialog(ft.SnackBar(content=ft.Text(msg)))

    # Contenedor principal para las transiciones entre pantallas
    content_area = ft.AnimatedSwitcher(
        content=ft.Container(),
        transition=ft.AnimatedSwitcherTransition.FADE,
        duration=400,
        reverse_duration=300,
    )

    # --- VISTA 1: Pantalla de Bienvenida ---
    def show_home(e=None):
        def hover_handler(contenedor):
            def handler(e):
                contenedor.scale = 1.05 if str(e.data).lower() == "true" else 1.0
                contenedor.update()
            return handler

        admin_btn = ft.Container(
            content=boton("Modo Administrador", ft.Icons.ADMIN_PANEL_SETTINGS,
                          ft.Colors.INDIGO, lambda _: show_admin_view()),
            scale=1.0,
            animate_scale=ft.Animation(duration=200, curve=ft.AnimationCurve.EASE_OUT),
        )
        admin_btn.on_hover = hover_handler(admin_btn)

        user_btn = ft.Container(
            content=boton("Modo Usuario", ft.Icons.SHOPPING_CART,
                          ft.Colors.TEAL, lambda _: show_user_view()),
            scale=1.0,
            animate_scale=ft.Animation(duration=200, curve=ft.AnimationCurve.EASE_OUT),
        )
        user_btn.on_hover = hover_handler(user_btn)

        home_view = ft.Column(
            [
                ft.Icon(ft.Icons.STOREFRONT, size=80, color=ft.Colors.PRIMARY),
                ft.Text("Bienvenido a la Tienda", size=24, weight=ft.FontWeight.BOLD),
                ft.Text("Selecciona tu rol para continuar", size=14, color=ft.Colors.GREY_700),
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                admin_btn,
                user_btn,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=15,
        )

        content_area.content = home_view
        page.update()

    # --- VISTA 2: Panel de Administrador ---
    def show_admin_view():
        product_list_column = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=10)

        # ---------- Formulario: agregar producto nuevo ----------
        nueva_imagen = {"path": None}

        nombre_input = ft.TextField(label="Nombre del producto", expand=True, dense=True, text_size=13)
        precio_nuevo_input = ft.TextField(label="Precio ($)", width=100, dense=True, text_size=13)
        imagen_label = ft.Text(
            "Sin imagen (se usará una de prueba)",
            size=11,
            color=ft.Colors.GREY_700,
            expand=True,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

        async def elegir_imagen_nueva(e):
            files = await file_picker.pick_files(
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["png", "jpg", "jpeg"],
            )
            if files:
                nueva_imagen["path"] = files[0].path
                imagen_label.value = files[0].name
                page.update()

        def agregar_producto(e):
            nombre = (nombre_input.value or "").strip()
            if not nombre:
                notify("Escribe un nombre para el producto.")
                return
            try:
                precio = parse_precio(precio_nuevo_input.value)
            except ValueError:
                notify("Por favor ingresa un precio válido.")
                return

            nuevo_id = max((p["id"] for p in productos), default=0) + 1
            productos.append({
                "id": nuevo_id,
                "name": nombre,
                "price": precio,
                "image": nueva_imagen["path"] or f"https://picsum.photos/200/200?random={nuevo_id}",
            })

            # Limpiar formulario
            nombre_input.value = ""
            precio_nuevo_input.value = ""
            nueva_imagen["path"] = None
            imagen_label.value = "Sin imagen (se usará una de prueba)"

            notify(f"¡'{nombre}' agregado a ${precio:.2f}!")
            update_product_list()

        formulario = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Agregar nuevo producto", weight=ft.FontWeight.BOLD, size=14),
                        ft.Row([nombre_input, precio_nuevo_input], spacing=10),
                        ft.Row(
                            [
                                ft.IconButton(
                                    icon=ft.Icons.IMAGE,
                                    tooltip="Elegir imagen",
                                    icon_size=20,
                                    on_click=elegir_imagen_nueva,
                                ),
                                imagen_label,
                                boton("Agregar", ft.Icons.ADD, ft.Colors.INDIGO, agregar_producto, radio=8),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=8,
                ),
                padding=10,
            )
        )

        # ---------- Compartir / importar productos por QR ----------
        def abrir_dialogo_qr(e):
            if not productos:
                notify("No hay productos para compartir.")
                return

            codigo = codificar_productos(productos)
            contenido = [ft.Text(f"{len(productos)} producto(s) en el código.", size=12)]
            try:
                ruta = generar_qr_png(codigo)
                contenido.append(ft.Image(src=ruta, width=280, height=280, fit=ft.BoxFit.CONTAIN))
            except ImportError:
                contenido.append(ft.Text("Para generar el QR instala:  pip install segno",
                                         color=ft.Colors.RED, size=12))
            except ValueError:
                contenido.append(ft.Text(
                    "Hay demasiados productos para caber en un solo QR. "
                    "Elimina algunos e inténtalo de nuevo.",
                    color=ft.Colors.RED, size=12))
            except Exception as ex:
                contenido.append(ft.Text(f"No se pudo generar el QR: {ex}",
                                         color=ft.Colors.RED, size=12))

            contenido += [
                ft.Text("Código de respaldo (cópialo y pégalo en el otro dispositivo):",
                        size=11, color=ft.Colors.GREY_700),
                ft.TextField(value=codigo, read_only=True, multiline=True,
                             min_lines=2, max_lines=3, text_size=10),
                ft.Text("Las imágenes elegidas desde tu computador no se transfieren: "
                        "esos productos usarán una imagen de prueba.",
                        size=11, color=ft.Colors.GREY_700),
            ]

            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Compartir productos por QR"),
                    content=ft.Column(contenido, tight=True, scroll=ft.ScrollMode.AUTO,
                                      horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                      spacing=8, width=300),
                    actions=[ft.TextButton("Cerrar", on_click=lambda _: page.pop_dialog())],
                )
            )

        def abrir_dialogo_importar(e):
            estado = ft.Text("", size=12)
            codigo_input = ft.TextField(label="Pega aquí el código", multiline=True,
                                        min_lines=2, max_lines=4, text_size=11)

            def mostrar(msg, ok=False):
                estado.value = msg
                estado.color = ft.Colors.GREEN_700 if ok else ft.Colors.RED
                page.update()

            def procesar(texto):
                try:
                    nuevos = decodificar_productos(texto)
                except ValueError as ex:
                    mostrar(str(ex))
                    return
                agregados, actualizados = importar_productos(nuevos)
                update_product_list()
                mostrar(f"Listo: {agregados} agregado(s), {actualizados} actualizado(s).", ok=True)

            async def escanear_camara(ev):
                mostrar("Abriendo la cámara... (Q para cancelar)", ok=True)
                try:
                    texto = await asyncio.to_thread(escanear_qr_camara)
                except ImportError:
                    mostrar("Instala OpenCV:  pip install opencv-python")
                    return
                except Exception as ex:
                    mostrar(str(ex))
                    return
                if texto:
                    procesar(texto)
                else:
                    mostrar("Escaneo cancelado.", ok=True)

            async def cargar_imagen(ev):
                files = await file_picker.pick_files(
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["png", "jpg", "jpeg"],
                )
                if not files:
                    return
                try:
                    texto = leer_qr_desde_imagen(files[0].path)
                except ImportError:
                    mostrar("Instala OpenCV:  pip install opencv-python")
                    return
                if texto:
                    procesar(texto)
                else:
                    mostrar("No se encontró un QR legible en esa imagen.")

            if es_movil:
                opciones_scan = [
                    ft.Text("Escanea el QR con la cámara de tu teléfono, copia el texto "
                            "que aparece y pégalo aquí abajo.",
                            size=12, color=ft.Colors.GREY_700),
                ]
            else:
                opciones_scan = [
                    boton("Escanear con la cámara", ft.Icons.QR_CODE_SCANNER,
                          ft.Colors.TEAL, escanear_camara, radio=8),
                    boton("Cargar imagen del QR", ft.Icons.IMAGE,
                          ft.Colors.INDIGO, cargar_imagen, radio=8),
                    ft.Divider(),
                ]

            page.show_dialog(
                ft.AlertDialog(
                    title=ft.Text("Importar productos"),
                    content=ft.Column(
                        [
                            *opciones_scan,
                            codigo_input,
                            boton("Importar código", ft.Icons.DOWNLOAD,
                                  ft.Colors.GREEN, lambda _: procesar(codigo_input.value), radio=8),
                            estado,
                        ],
                        tight=True, scroll=ft.ScrollMode.AUTO, spacing=8, width=300,
                    ),
                    actions=[ft.TextButton("Cerrar", on_click=lambda _: page.pop_dialog())],
                )
            )

        acciones_qr = ft.Row(
            [
                boton("Compartir por QR", ft.Icons.QR_CODE, ft.Colors.TEAL, abrir_dialogo_qr, radio=8),
                boton("Importar", ft.Icons.QR_CODE_SCANNER, ft.Colors.INDIGO, abrir_dialogo_importar, radio=8),
            ],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        )

        # ---------- Lista de productos existentes ----------
        def save_changes(prod, new_price_str):
            try:
                prod["price"] = parse_precio(new_price_str)
                notify(f"¡Precio de {prod['name']} actualizado a ${prod['price']:.2f}!")
            except ValueError:
                notify("Por favor ingresa un precio válido.")

        def make_save_handler(prod, inp):
            return lambda _: save_changes(prod, inp.value)

        def make_delete_handler(prod):
            def delete(e):
                productos.remove(prod)
                # Quitar también del carrito si estaba
                carrito[:] = [item for item in carrito if item["id"] != prod["id"]]
                notify(f"'{prod['name']}' eliminado.")
                update_product_list()
            return delete

        def make_image_handler(prod):
            async def pick_image(e):
                files = await file_picker.pick_files(
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=["png", "jpg", "jpeg"],
                )
                if files:
                    prod["image"] = files[0].path
                    notify("¡Imagen actualizada con éxito!")
                    update_product_list()
            return pick_image

        def update_product_list():
            product_list_column.controls.clear()
            for p in productos:
                price_input = ft.TextField(
                    value=str(p["price"]),
                    label="Precio ($)",
                    width=100,
                    text_size=12,
                    dense=True,
                )

                product_list_column.controls.append(
                    ft.Card(
                        content=ft.Container(
                            content=ft.Row(
                                [
                                    ft.Image(src=p["image"], width=50, height=50,
                                             border_radius=8, fit=ft.BoxFit.COVER),
                                    ft.Column(
                                        [
                                            ft.Text(p["name"], weight=ft.FontWeight.BOLD, size=14),
                                            price_input,
                                        ],
                                        expand=True,
                                        spacing=2,
                                    ),
                                    ft.Row(
                                        [
                                            ft.IconButton(
                                                icon=ft.Icons.IMAGE,
                                                tooltip="Cambiar Imagen",
                                                icon_size=20,
                                                on_click=make_image_handler(p),
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.SAVE,
                                                tooltip="Guardar Precio",
                                                icon_color=ft.Colors.GREEN,
                                                icon_size=20,
                                                on_click=make_save_handler(p, price_input),
                                            ),
                                            ft.IconButton(
                                                icon=ft.Icons.DELETE,
                                                tooltip="Eliminar producto",
                                                icon_color=ft.Colors.RED,
                                                icon_size=20,
                                                on_click=make_delete_handler(p),
                                            ),
                                        ],
                                        spacing=0,
                                    ),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            padding=10,
                        )
                    )
                )
            page.update()

        admin_view = ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=show_home),
                        ft.Text("Panel de Administración", size=18, weight=ft.FontWeight.BOLD),
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
                formulario,
                acciones_qr,
                ft.Text("Modifica precios o actualiza imágenes de productos:",
                        size=12, color=ft.Colors.GREY_700),
                ft.Divider(),
                product_list_column,
            ],
            expand=True,
            spacing=10,
        )

        content_area.content = ft.Container(content=admin_view, padding=15)
        update_product_list()
        page.update()

    # --- VISTA 3: Panel de Usuario ---
    def show_user_view():
        total_text = ft.Text("Total: $0.00", weight=ft.FontWeight.BOLD, size=16,
                             color=ft.Colors.GREEN_700)
        cart_badge = ft.Text("0", color=ft.Colors.BLACK, size=12)

        products_grid = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=10)

        qty_texts = {}   # id de producto -> Text con la cantidad
        minus_btns = {}  # id de producto -> botón de restar

        def cantidad(pid):
            return sum(1 for item in carrito if item["id"] == pid)

        def update_total():
            total = sum(item["price"] for item in carrito)
            total_text.value = f"Total: ${total:.2f}"
            cart_badge.value = str(len(carrito))
            for pid, txt in qty_texts.items():
                q = cantidad(pid)
                txt.value = str(q)
                minus_btns[pid].disabled = (q == 0)
            page.update()

        def add_to_cart(product):
            carrito.append(product)
            update_total()
            notify(f"'{product['name']}' agregado al carro")

        def remove_from_cart(product):
            for i in range(len(carrito) - 1, -1, -1):
                if carrito[i]["id"] == product["id"]:
                    carrito.pop(i)
                    break
            else:
                return  # no había unidades de este producto
            update_total()
            notify(f"Se quitó una unidad de '{product['name']}'")

        def clear_cart():
            if not carrito:
                notify("El carro está vacío.")
            else:
                carrito.clear()
                update_total()
                notify("¡Compra realizada con éxito!")

        def make_add_handler(prod):
            return lambda _: add_to_cart(prod)

        def make_remove_handler(prod):
            return lambda _: remove_from_cart(prod)

        if not productos:
            products_grid.controls.append(
                ft.Text("Aún no hay productos disponibles.", color=ft.Colors.GREY_700)
            )

        for p in productos:
            qty_text = ft.Text("0", width=24, text_align=ft.TextAlign.CENTER,
                               weight=ft.FontWeight.BOLD)
            minus_btn = ft.IconButton(
                icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                icon_color=ft.Colors.RED,
                tooltip="Quitar una unidad",
                on_click=make_remove_handler(p),
                disabled=True,
            )
            qty_texts[p["id"]] = qty_text
            minus_btns[p["id"]] = minus_btn

            products_grid.controls.append(
                ft.Card(
                    content=ft.Container(
                        content=ft.Row(
                            [
                                ft.Image(src=p["image"], width=60, height=60,
                                         border_radius=8, fit=ft.BoxFit.COVER),
                                ft.Column(
                                    [
                                        ft.Text(p["name"], weight=ft.FontWeight.BOLD, size=14),
                                        ft.Text(f"${p['price']:.2f}", color=ft.Colors.GREEN,
                                                weight=ft.FontWeight.W_600),
                                    ],
                                    expand=True,
                                    spacing=2,
                                ),
                                ft.Row(
                                    [
                                        minus_btn,
                                        qty_text,
                                        ft.IconButton(
                                            icon=ft.Icons.ADD_CIRCLE_OUTLINE,
                                            icon_color=ft.Colors.TEAL,
                                            tooltip="Añadir una unidad",
                                            on_click=make_add_handler(p),
                                        ),
                                    ],
                                    spacing=0,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        padding=10,
                    )
                )
            )

        user_view = ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=show_home),
                        ft.Text("Catálogo de Productos", size=18, weight=ft.FontWeight.BOLD),
                        ft.Row([ft.Icon(ft.Icons.SHOPPING_BAG, color=ft.Colors.TEAL), cart_badge],
                               spacing=2),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(),
                products_grid,
                ft.Container(
                    content=ft.Row(
                        [
                            total_text,
                            boton("Pagar", ft.Icons.CHECK, ft.Colors.GREEN,
                                  lambda _: clear_cart()),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=10,
                    bgcolor=ft.Colors.WHITE,
                    border_radius=10,
                ),
            ],
            expand=True,
            spacing=10,
        )

        content_area.content = ft.Container(content=user_view, padding=15)
        update_total()
        page.update()

    show_home()

    page.add(
        ft.SafeArea(expand=True, content=ft.Container(
            content=content_area,
            expand=True,
            bgcolor=ft.Colors.WHITE,
            border_radius=15,
            margin=10,
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=10, color=ft.Colors.BLACK_12),
        ))
    )


ft.run(main)
