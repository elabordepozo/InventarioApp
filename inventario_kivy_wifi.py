"""
inventario_kivy_wifi.py — Aplicación Android/Escritorio (Kivy)
Requiere: kivy
Escaneo (opcional): zxing-cpp y/o pyzbar + Pillow
  - Pydroid 3 (sin OpenCV premium): pip install zxing-cpp Pillow
  - pyzbar opcional (EAN/UPC); en Android a veces falla por librerias nativas.

Nota Android: la UI evita emojis en botones para no ver cuadrados con cruz (tofu).
"""

import os, sys, json, threading

# ── Path a data_manager.py ─────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_manager as dm

# ── Kivy config ANTES de importar Kivy ────────────────────────────────────────
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.utils import get_color_from_hex as hex_c
from kivy.clock import Clock
from datetime import datetime

# Colores
BG      = hex_c("#1e2b38")
PANEL   = hex_c("#253545")
CARD    = hex_c("#2d4059")
ACCENT  = hex_c("#3498db")
SUCCESS = hex_c("#27ae60")
DANGER  = hex_c("#e74c3c")
WARN    = hex_c("#f39c12")
TEXT    = hex_c("#ecf0f1")
MUTED   = hex_c("#95a5a6")

Window.clearcolor = BG

# ── Helpers ────────────────────────────────────────────────────────────────────
def mk_btn(text, on_press, bg=None, height=dp(48), **kw):
    bg = bg or ACCENT
    b = Button(text=text, size_hint_y=None, height=height,
               background_normal="", background_color=bg,
               color=TEXT, font_size=dp(14), bold=True,
               on_press=on_press, **kw)
    return b

def mk_lbl(text, size=dp(13), color=None, bold=False, **kw):
    return Label(text=text, font_size=size, color=color or TEXT,
                 bold=bold, halign="left", **kw)

def mk_input(hint="", **kw):
    return TextInput(hint_text=hint, multiline=False,
                     background_color=hex_c("#1a2530"),
                     foreground_color=TEXT, hint_text_color=MUTED,
                     cursor_color=TEXT, font_size=dp(13),
                     size_hint_y=None, height=dp(42), **kw)

def alerta(titulo, mensaje, btn_texto="OK", on_dismiss=None):
    content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
    content.add_widget(Label(text=mensaje, color=TEXT, font_size=dp(13),
                              text_size=(None, None)))
    p = Popup(title=titulo, content=content, size_hint=(0.85, None),
              height=dp(200),
              title_color=ACCENT, separator_color=ACCENT,
              background_color=CARD)
    btn_ok = Button(text=btn_texto, size_hint_y=None, height=dp(40),
                    background_normal="", background_color=ACCENT,
                    color=TEXT, font_size=dp(13),
                    on_press=lambda _: (p.dismiss(), on_dismiss() if on_dismiss else None))
    content.add_widget(btn_ok)
    p.open()
    return p

def confirmar(titulo, mensaje, on_yes):
    content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
    content.add_widget(Label(text=mensaje, color=TEXT, font_size=dp(13)))
    bts = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(44))
    p = Popup(title=titulo, content=content, size_hint=(0.85, None),
              height=dp(200), title_color=WARN, separator_color=WARN,
              background_color=CARD)
    bts.add_widget(Button(text="Sí", background_normal="", background_color=DANGER,
                          color=TEXT, font_size=dp(13),
                          on_press=lambda _: (p.dismiss(), on_yes())))
    bts.add_widget(Button(text="Cancelar", background_normal="",
                          background_color=MUTED, color=TEXT, font_size=dp(13),
                          on_press=lambda _: p.dismiss()))
    content.add_widget(bts)
    p.open()


# ── Escaneo cámara (QR y códigos de barras si hay backend) ────────────────────
def _camara_kivy_disponible():
    try:
        from kivy.uix.camera import Camera  # noqa: F401
        return True
    except ImportError:
        return False


def _hay_decodificador():
    try:
        import zxingcpp  # noqa: F401
        if hasattr(zxingcpp, "read_barcodes"):
            return True
    except ImportError:
        pass
    try:
        from pyzbar import pyzbar  # noqa: F401
        return True
    except ImportError:
        pass
    return False


def escaneo_puede_funcionar():
    if not _camara_kivy_disponible():
        return False, (
            "El modulo Camera de Kivy no esta disponible en este entorno.")
    if not _hay_decodificador():
        return False, (
            "No hay lector de codigos instalado.\n\n"
            "En Pydroid 3 (OpenCV suele ser de pago): usa Pip sin premium:\n"
            "  zxing-cpp\n"
            "  Pillow\n\n"
            "Reinicia la app. Opcional: pyzbar (si tu movil lo carga).\n"
            "Si no instalas nada, puedes escribir el codigo a mano.")
    return True, ""


def _variants_gray(gray):
    """Variantes de orientacion sin OpenCV (solo numpy + Pillow)."""
    import numpy as np
    from PIL import Image as PILImage

    g = np.ascontiguousarray(gray)
    out = [g, np.ascontiguousarray(np.flipud(g)), np.ascontiguousarray(np.fliplr(g))]
    pil0 = PILImage.fromarray(g, mode="L")
    for angle in (90, 180, 270):
        out.append(np.ascontiguousarray(
            np.array(pil0.rotate(angle, expand=True), dtype=np.uint8)))
    return out


def _try_zxingcpp_pil(pil_img):
    """Lee QR y muchos codigos de barras 1D (paquete pip: zxing-cpp)."""
    try:
        import zxingcpp

        rgb = pil_img.convert("RGB")
        for im in _pil_variants_rgb(rgb):
            try:
                for bc in zxingcpp.read_barcodes(im):
                    txt = getattr(bc, "text", None)
                    if txt and str(txt).strip():
                        return str(txt).strip()
            except Exception:
                continue
    except Exception:
        pass
    return None


def _pil_variants_rgb(rgb):
    from PIL import Image as PILImage

    imgs = [rgb]
    imgs.append(rgb.transpose(PILImage.FLIP_TOP_BOTTOM))
    imgs.append(rgb.transpose(PILImage.FLIP_LEFT_RIGHT))
    for a in (90, 180, 270):
        imgs.append(rgb.rotate(a, expand=True))
    return imgs


def _try_pyzbar(gray):
    try:
        from pyzbar import pyzbar
        for g in _variants_gray(gray):
            for sym in pyzbar.decode(g):
                t = sym.data.decode("utf-8", errors="replace").strip()
                if t:
                    return t
    except Exception:
        pass
    return None


def decodificar_textura_camera(texture):
    """Devuelve el texto del primer codigo detectado, o None."""
    w, h = texture.size
    try:
        from PIL import Image as PILImage

        pil_rgba = PILImage.frombytes("RGBA", (w, h), texture.pixels)
        t = _try_zxingcpp_pil(pil_rgba)
        if t:
            return t
        import numpy as np
        gray = np.array(pil_rgba.convert("L"))
    except Exception:
        import numpy as np
        arr = np.frombuffer(texture.pixels, dtype=np.uint8).reshape((h, w, 4))
        gray = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1]
                + 0.114 * arr[:, :, 2]).astype(np.uint8)
    return _try_pyzbar(gray)


def _detener_cam(cam):
    if cam:
        try:
            cam.play = False
        except Exception:
            pass


# ── Permiso de cámara en tiempo de ejecución (Android 6+) ────────────────────
def _pedir_permiso_camara(callback_si, callback_no=None):
    """
    En Android solicita el permiso CAMERA en tiempo de ejecución.
    En escritorio llama directamente a callback_si().
    """
    try:
        from android.permissions import request_permissions, Permission, check_permission
        if check_permission(Permission.CAMERA):
            callback_si()
        else:
            def _on_perms(perms, grants):
                if grants and all(grants):
                    callback_si()
                else:
                    if callback_no:
                        callback_no()
                    else:
                        alerta("Permiso denegado",
                               "La app necesita permiso de camara para escanear.\n"
                               "Ve a Ajustes > Aplicaciones > Inventario > Permisos.")
            request_permissions([Permission.CAMERA], _on_perms)
    except ImportError:
        # No estamos en Android (escritorio/Pydroid sin módulo android)
        callback_si()


def abrir_escaneo_camara(callback_codigo, titulo="Escanear codigo"):
    """
    Pide permiso de cámara (Android) y luego abre el visor.
    Al pulsar Capturar se decodifica y se llama callback_codigo(str).
    """
    def _abrir():
        ok, err = escaneo_puede_funcionar()
        if not ok:
            alerta("Escaneo", err)
            return
        from kivy.uix.camera import Camera

        cam_holder = [None]
        cam_layout = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        cam = Camera(play=True, resolution=(640, 480))
        cam_holder[0] = cam
        cam_layout.add_widget(cam)

        cam_pop = Popup(title=titulo, content=cam_layout, size_hint=(0.95, 0.78),
                        background_color=CARD, title_color=ACCENT,
                        separator_color=ACCENT)

        def capturar(_):
            c = cam_holder[0]
            if not c or not c.texture:
                alerta("Camara", "Espera un momento a que arranque la imagen.")
                return
            try:
                cod = decodificar_textura_camera(c.texture)
                if cod:
                    cam_pop.dismiss()
                    c.play = False
                    callback_codigo(cod)
                else:
                    alerta("Sin resultado",
                           "No se leyo ningun codigo.\n"
                           "Mejora la luz, acerca el codigo.")
            except Exception as e:
                alerta("Error", str(e))

        cam_layout.add_widget(mk_btn("Capturar", capturar, bg=SUCCESS, height=dp(48)))
        cam_pop.bind(on_dismiss=lambda *_: _detener_cam(cam_holder[0]))
        cam_pop.open()

    # Primero pedir permiso, luego abrir
    _pedir_permiso_camara(_abrir)


# ── Pantalla base ──────────────────────────────────────────────────────────────
class PantallaBase(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.root_layout = BoxLayout(orientation="vertical", spacing=0)
        self._header()
        self.body = BoxLayout(orientation="vertical", padding=dp(10),
                              spacing=dp(8))
        self.root_layout.add_widget(self.body)
        self.add_widget(self.root_layout)

    def _header(self):
        h = BoxLayout(size_hint_y=None, height=dp(52),
                      padding=(dp(10), dp(6)),
                      spacing=dp(8))
        h.canvas.before.add(
            __import__("kivy.graphics", fromlist=["Color"]).Color(*PANEL))
        from kivy.graphics import Rectangle
        h.canvas.before.add(Rectangle(pos=h.pos, size=h.size))

        if self.name != "menu":
            btn_back = Button(text="<", size_hint=(None, None),
                              width=dp(44), height=dp(40),
                              background_normal="", background_color=CARD,
                              color=ACCENT, font_size=dp(16), bold=True,
                              on_press=lambda _: self._volver())
            h.add_widget(btn_back)

        h.add_widget(Label(text=self._titulo(),
                           font_size=dp(15), bold=True, color=TEXT))
        self.root_layout.add_widget(h)

    def _titulo(self): return ""
    def _volver(self):
        self.manager.transition = SlideTransition(direction="right")
        self.manager.current = "menu"

    # ── Método de recarga post-sincronización ─────────────────────────────────
    def refresh(self):
        """
        Llamado por SyncScreen después de una sincronización exitosa.
        Cada subclase lo sobreescribe para recargar sus datos desde disco.
        Solo actúa si la pantalla ya fue construida (body tiene widgets).
        """
        pass

# ══════════════════════════════════════════════════════════════════════════════
# MENÚ PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
class MenuScreen(Screen):
    def _titulo(self): return "Menú"

    def __init__(self, **kw):
        super().__init__(**kw)
        dm.inicializar()
        layout = BoxLayout(orientation="vertical", padding=dp(20),
                           spacing=dp(14))
        layout.add_widget(Label(text="Inventario y Ventas",
                                font_size=dp(20), bold=True, color=ACCENT,
                                size_hint_y=None, height=dp(60)))
        botones = [
            ("Inventario",  "inventario", ACCENT),
            ("Ventas",      "ventas",     SUCCESS),
            ("Reportes",    "reportes",   WARN),
            ("Sincronizar", "sync",       hex_c("#8e44ad")),
        ]
        for texto, pantalla, color in botones:
            layout.add_widget(mk_btn(texto, lambda _, s=pantalla: self._ir(s),
                                     bg=color, height=dp(60)))
        self.add_widget(layout)

    def _ir(self, pantalla):
        self.manager.transition = SlideTransition(direction="left")
        self.manager.current = pantalla

# ══════════════════════════════════════════════════════════════════════════════
# INVENTARIO
# ══════════════════════════════════════════════════════════════════════════════
class InventarioScreen(PantallaBase):
    def _titulo(self): return "Inventario"

    def on_enter(self):
        self.body.clear_widgets()
        self._construir()

    # ── NUEVO: recarga post-sync sin reconstruir toda la pantalla ─────────────
    def refresh(self):
        if hasattr(self, "lista"):
            self._cargar()

    def _construir(self):
        # Buscador
        fila_bus = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.inp_buscar = mk_input("Buscar producto...")
        fila_bus.add_widget(self.inp_buscar)
        fila_bus.add_widget(mk_btn("Bus", lambda _: self._filtrar(),
                                   bg=PANEL, height=dp(44),
                                   size_hint_x=None, width=dp(48)))
        self.body.add_widget(fila_bus)

        # Botón agregar
        self.body.add_widget(mk_btn("+ Agregar producto",
                                    lambda _: self._dlg_producto(),
                                    bg=SUCCESS, height=dp(42)))

        # Lista
        scroll = ScrollView()
        self.lista = GridLayout(cols=1, spacing=dp(4),
                                size_hint_y=None, padding=(0, dp(4)))
        self.lista.bind(minimum_height=self.lista.setter("height"))
        scroll.add_widget(self.lista)
        self.body.add_widget(scroll)
        self._cargar()

    def _cargar(self, productos=None):
        self.lista.clear_widgets()
        if productos is None:
            productos = dm.leer_inventario()
        for p in productos:
            self._fila_producto(p)

    def _filtrar(self):
        txt = self.inp_buscar.text.strip()
        self._cargar(dm.buscar_por_nombre(txt) if txt else None)

    def _fila_producto(self, p):
        row = BoxLayout(size_hint_y=None, height=dp(64),
                        spacing=dp(6), padding=(dp(8), dp(4)))
        from kivy.graphics import Color, RoundedRectangle
        with row.canvas.before:
            Color(*CARD)
            row._rect = RoundedRectangle(pos=row.pos, size=row.size, radius=[dp(6)])
        row.bind(pos=lambda w, v: setattr(w._rect, "pos", v),
                 size=lambda w, v: setattr(w._rect, "size", v))

        info = BoxLayout(orientation="vertical", spacing=2)
        stock_color = "#f39c12" if int(p["stock"]) <= 5 else "#ecf0f1"
        info.add_widget(Label(text=p["nombre"], font_size=dp(13), bold=True,
                              color=TEXT, halign="left",
                              size_hint_y=None, height=dp(22)))
        info.add_widget(Label(
            text=f"Cód: {p['codigo']}  |  $ {float(p['precio']):.2f}  |  "
                 f"[color={stock_color}]Stock: {p['stock']}[/color]",
            font_size=dp(11), color=MUTED, halign="left", markup=True,
            size_hint_y=None, height=dp(18)))
        row.add_widget(info)

        acciones = BoxLayout(size_hint_x=None, width=dp(84), spacing=dp(4))
        acciones.add_widget(mk_btn("Ed", lambda _, pr=p: self._dlg_producto(pr),
                                   bg=WARN, height=dp(38),
                                   size_hint_x=None, width=dp(38)))
        acciones.add_widget(mk_btn("X", lambda _, pr=p: self._eliminar(pr),
                                   bg=DANGER, height=dp(38),
                                   size_hint_x=None, width=dp(38)))
        row.add_widget(acciones)
        self.lista.add_widget(row)

    def _dlg_producto(self, producto=None):
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
        campos = {
            "nombre":  mk_input("Nombre del producto"),
            "precio":  mk_input("Precio (CUP)", input_filter="float"),
            "stock":   mk_input("Stock inicial", input_filter="int"),
        }
        cod_in = mk_input("Codigo de barras o QR")
        campos["codigo"] = cod_in
        if producto:
            campos["nombre"].text = producto["nombre"]
            cod_in.text = producto["codigo"]
            campos["precio"].text = producto["precio"]
            campos["stock"].text  = producto["stock"]

        content.add_widget(campos["nombre"])
        fila_cod = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        cod_in.size_hint_x = 1
        fila_cod.add_widget(cod_in)
        fila_cod.add_widget(mk_btn(
            "Cam", lambda _: abrir_escaneo_camara(lambda c: setattr(cod_in, "text", c)),
            bg=PANEL, height=dp(42), size_hint_x=None, width=dp(56)))
        content.add_widget(fila_cod)
        content.add_widget(campos["precio"])
        content.add_widget(campos["stock"])

        p = Popup(title="Editar" if producto else "Nuevo Producto",
                  content=content, size_hint=(0.92, None), height=dp(400),
                  title_color=ACCENT, separator_color=ACCENT,
                  background_color=CARD)

        def guardar(_):
            nombre = campos["nombre"].text.strip()
            codigo = campos["codigo"].text.strip()
            try:
                precio = float(campos["precio"].text or 0)
                stock  = int(campos["stock"].text   or 0)
            except ValueError:
                alerta("Error", "Precio y Stock deben ser números.")
                return
            if not nombre:
                alerta("Error", "El nombre es obligatorio.")
                return
            if producto:
                dm.editar_producto(producto["id"], nombre, codigo, precio, stock)
            else:
                dm.agregar_producto(nombre, codigo, precio, stock)
            p.dismiss()
            self._cargar()

        bts = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        bts.add_widget(mk_btn("Guardar", guardar, bg=SUCCESS))
        bts.add_widget(mk_btn("Cancelar", lambda _: p.dismiss(), bg=MUTED))
        content.add_widget(bts)
        p.open()

    def _eliminar(self, p):
        confirmar("¿Eliminar?", f"Eliminar '{p['nombre']}'",
                  lambda: (dm.eliminar_producto(p["id"]), self._cargar()))

# ══════════════════════════════════════════════════════════════════════════════
# VENTAS
# ══════════════════════════════════════════════════════════════════════════════
class VentasScreen(PantallaBase):
    def _titulo(self): return "Nueva venta"

    def on_enter(self):
        self.body.clear_widgets()
        self._prod_sel = None
        self._construir()

    # ── NUEVO: recarga post-sync ───────────────────────────────────────────────
    def refresh(self):
        if hasattr(self, "_prods"):
            self._cargar_prods()
        if hasattr(self, "lista_v"):
            self._cargar_ventas_hoy()

    def _construir(self):
        # Escaneo / búsqueda
        self.body.add_widget(Label(text="Buscar o escanear producto",
                                    color=MUTED, font_size=dp(12),
                                    size_hint_y=None, height=dp(20)))

        fila_cod = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.inp_cod = mk_input("Código de barras / QR")
        fila_cod.add_widget(self.inp_cod)
        fila_cod.add_widget(mk_btn("OK", lambda _: self._buscar_cod(),
                                   bg=ACCENT, height=dp(44),
                                   size_hint_x=None, width=dp(50)))

        fila_cod.add_widget(mk_btn("Cam", lambda _: self._escanear_camara(),
                                   bg=PANEL, height=dp(44),
                                   size_hint_x=None, width=dp(50)))
        self.body.add_widget(fila_cod)

        fila_nom = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.inp_nom = mk_input("Nombre del producto")
        fila_nom.add_widget(self.inp_nom)
        fila_nom.add_widget(mk_btn("Bus", lambda _: self._buscar_nom(),
                                   bg=ACCENT, height=dp(44),
                                   size_hint_x=None, width=dp(50)))
        self.body.add_widget(fila_nom)

        # Spinner de resultados
        self.spinner = Spinner(text="Selecciona un producto...",
                               values=[],
                               size_hint_y=None, height=dp(44),
                               background_normal="", background_color=CARD,
                               color=TEXT, font_size=dp(12))
        self.spinner.bind(text=self._al_seleccionar)
        self.body.add_widget(self.spinner)

        # Info producto seleccionado
        self.lbl_info = Label(text="Precio: -   Stock: -",
                              color=ACCENT, font_size=dp(13), bold=True,
                              size_hint_y=None, height=dp(28))
        self.body.add_widget(self.lbl_info)

        # Cantidad
        fila_cant = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        fila_cant.add_widget(Label(text="Cantidad:", color=TEXT,
                                    font_size=dp(13), size_hint_x=None,
                                    width=dp(90)))
        self.inp_cant = mk_input("1", input_filter="int")
        self.inp_cant.text = "1"
        fila_cant.add_widget(self.inp_cant)
        self.body.add_widget(fila_cant)

        self.body.add_widget(mk_btn("REGISTRAR VENTA",
                                    lambda _: self._vender(), bg=SUCCESS,
                                    height=dp(52)))

        # Historial hoy
        self.body.add_widget(Label(text="- Ventas de hoy -",
                                    color=MUTED, font_size=dp(11),
                                    size_hint_y=None, height=dp(24)))
        scroll = ScrollView()
        self.lista_v = GridLayout(cols=1, spacing=dp(4),
                                   size_hint_y=None)
        self.lista_v.bind(minimum_height=self.lista_v.setter("height"))
        scroll.add_widget(self.lista_v)
        self.body.add_widget(scroll)
        self._cargar_prods()
        self._cargar_ventas_hoy()

    def _cargar_prods(self):
        self._prods = dm.leer_inventario()
        self.spinner.values = [f"{p['nombre']}  ($ {float(p['precio']):.2f}  |  {p['stock']} uds)"
                                for p in self._prods]

    def _buscar_cod(self):
        cod = self.inp_cod.text.strip()
        p = dm.buscar_por_codigo(cod)
        if p:
            self._seleccionar_prod(p)
        else:
            alerta("No encontrado", f"Código '{cod}' no hallado.")

    def _buscar_nom(self):
        txt = self.inp_nom.text.strip()
        if not txt:
            return
        res = dm.buscar_por_nombre(txt)
        if not res:
            alerta("No encontrado", "Sin resultados.")
            return
        self._prods_filtrados = res
        self.spinner.values = [f"{p['nombre']}  ($ {float(p['precio']):.2f}  |  {p['stock']} uds)"
                                for p in res]
        self._prods = res

    def _seleccionar_prod(self, p):
        self._prod_sel = p
        self.lbl_info.text = (f"Precio: $ {float(p['precio']):.2f}   "
                               f"Stock: {p['stock']}")

    def _al_seleccionar(self, spinner, texto):
        idx = list(spinner.values).index(texto) if texto in spinner.values else -1
        if idx >= 0 and self._prods:
            self._seleccionar_prod(self._prods[idx])

    def _escanear_camara(self):
        def al_leer(cod):
            self.inp_cod.text = cod
            self._buscar_cod()

        abrir_escaneo_camara(al_leer, titulo="Escanear codigo (venta)")

    def _vender(self):
        if not self._prod_sel:
            alerta("Atención", "Selecciona un producto.")
            return
        try:
            cant = int(self.inp_cant.text or 0)
            if cant <= 0: raise ValueError
        except ValueError:
            alerta("Error", "Cantidad debe ser un entero positivo.")
            return

        ok, res = dm.registrar_venta(self._prod_sel["id"],
                                      self._prod_sel["nombre"],
                                      cant, self._prod_sel["precio"])
        if ok:
            alerta("Venta registrada",
                   f"Producto : {res['producto_nombre']}\n"
                   f"Cantidad : {cant}\n"
                   f"Total    : $ {float(res['total']):.2f}",
                   on_dismiss=lambda: (self._cargar_prods(),
                                       self._cargar_ventas_hoy()))
            self._prod_sel = None
            self.lbl_info.text = "Precio: -   Stock: -"
            self.inp_cant.text = "1"
        else:
            alerta("Error", res)

    def _cargar_ventas_hoy(self):
        self.lista_v.clear_widgets()
        for v in dm.ventas_hoy():
            txt = (f"[b]{v['producto_nombre']}[/b]  x{v['cantidad']}  "
                   f"-> $ {float(v['total']):.2f}  [{v['fecha'][11:16]}]")
            self.lista_v.add_widget(
                Label(text=txt, markup=True, color=TEXT, font_size=dp(12),
                      size_hint_y=None, height=dp(30), halign="left"))

# ══════════════════════════════════════════════════════════════════════════════
# REPORTES
# ══════════════════════════════════════════════════════════════════════════════
class ReportesScreen(PantallaBase):
    def _titulo(self): return "Reportes"

    def on_enter(self):
        self.body.clear_widgets()
        self._construir()

    # ── NUEVO: recarga post-sync ───────────────────────────────────────────────
    def refresh(self):
        if hasattr(self, "_cards"):
            self._ver_hoy()

    def _construir(self):
        # Filtros
        fila_f = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        anio_actual = str(datetime.now().year)
        mes_actual  = datetime.now().month

        fila_f.add_widget(Label(text="Año:", color=TEXT, font_size=dp(13),
                                 size_hint_x=None, width=dp(36)))
        self.inp_anio = mk_input(anio_actual)
        self.inp_anio.text = anio_actual
        fila_f.add_widget(self.inp_anio)

        meses = ["Ene","Feb","Mar","Abr","May","Jun",
                 "Jul","Ago","Sep","Oct","Nov","Dic"]
        self.spin_mes = Spinner(text=meses[mes_actual - 1], values=meses,
                                size_hint_y=None, height=dp(44),
                                background_normal="", background_color=CARD,
                                color=TEXT, font_size=dp(13))
        fila_f.add_widget(self.spin_mes)
        self.body.add_widget(fila_f)

        bts = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        bts.add_widget(mk_btn("Ver mes", lambda _: self._ver_mes(), bg=ACCENT))
        bts.add_widget(mk_btn("Hoy", lambda _: self._ver_hoy(), bg=WARN))
        self.body.add_widget(bts)

        # Tarjetas resumen
        self.card_row = BoxLayout(size_hint_y=None, height=dp(70), spacing=dp(6))
        self._cards = {}
        for key, titulo in [("num_ventas", "Ventas"),
                              ("items_vendidos", "Ítems"),
                              ("total_ingresos", "Total $")]:
            c = BoxLayout(orientation="vertical", padding=dp(6))
            from kivy.graphics import Color, RoundedRectangle
            with c.canvas.before:
                Color(*CARD)
                c._rect = RoundedRectangle(pos=c.pos, size=c.size, radius=[dp(8)])
            c.bind(pos=lambda w, v: setattr(w._rect, "pos", v),
                   size=lambda w, v: setattr(w._rect, "size", v))
            c.add_widget(Label(text=titulo, font_size=dp(11), color=MUTED))
            val = Label(text="-", font_size=dp(18), bold=True, color=ACCENT)
            c.add_widget(val)
            self._cards[key] = val
            self.card_row.add_widget(c)
        self.body.add_widget(self.card_row)

        # Detalle
        self.body.add_widget(Label(text="Detalle de ventas:",
                                    color=MUTED, font_size=dp(11),
                                    size_hint_y=None, height=dp(22)))
        scroll = ScrollView()
        self.lista_r = GridLayout(cols=1, spacing=dp(3),
                                   size_hint_y=None)
        self.lista_r.bind(minimum_height=self.lista_r.setter("height"))
        scroll.add_widget(self.lista_r)
        self.body.add_widget(scroll)
        self._ver_hoy()

    def _ver_mes(self):
        meses = ["Ene","Feb","Mar","Abr","May","Jun",
                 "Jul","Ago","Sep","Oct","Nov","Dic"]
        try:
            anio = int(self.inp_anio.text)
            mes  = meses.index(self.spin_mes.text) + 1
        except (ValueError, AttributeError):
            alerta("Error", "Año o mes inválido.")
            return
        self._render(dm.ventas_mes(anio, mes))

    def _ver_hoy(self):
        self._render(dm.ventas_hoy())

    def _render(self, ventas):
        res = dm.resumen(ventas)
        self._cards["num_ventas"].text     = str(res["num_ventas"])
        self._cards["items_vendidos"].text = str(res["items_vendidos"])
        self._cards["total_ingresos"].text = f"${res['total_ingresos']:.2f}"

        self.lista_r.clear_widgets()
        for v in ventas:
            txt = (f"[b]{v['fecha'][5:16]}[/b]  {v['producto_nombre']}  "
                   f"x{v['cantidad']}  = $ {float(v['total']):.2f}")
            self.lista_r.add_widget(
                Label(text=txt, markup=True, color=TEXT, font_size=dp(12),
                      size_hint_y=None, height=dp(28), halign="left"))

# ══════════════════════════════════════════════════════════════════════════════
# SINCRONIZAR — WiFi
# ══════════════════════════════════════════════════════════════════════════════
class SyncScreen(PantallaBase):
    def _titulo(self): return "Sincronizar WiFi"

    def on_enter(self):
        self.body.clear_widgets()
        self._construir()

    def _construir(self):
        # IP del servidor (PC)
        self.body.add_widget(Label(
            text="Dirección IP del servidor (PC):",
            color=MUTED, font_size=dp(12),
            size_hint_y=None, height=dp(22)))

        fila_ip = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.inp_ip = mk_input("Ej: http://192.168.1.5:8765")
        self._cargar_ip_guardada()
        fila_ip.add_widget(self.inp_ip)
        fila_ip.add_widget(mk_btn("OK", lambda _: self._guardar_ip(),
                                   bg=PANEL, height=dp(44),
                                   size_hint_x=None, width=dp(44)))
        self.body.add_widget(fila_ip)

        # Botón verificar conexión
        self.body.add_widget(mk_btn("Verificar conexión con la PC",
                                    lambda _: self._ping(),
                                    bg=hex_c("#8e44ad"), height=dp(44)))

        # Modo
        modo_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        modo_row.add_widget(Label(text="Modo:", color=TEXT, font_size=dp(13),
                                   size_hint_x=None, width=dp(50)))
        self.tb_combinar = ToggleButton(
            text="Combinar", group="modo_wifi", state="down",
            background_normal="", background_down="",
            background_color=SUCCESS, color=TEXT, font_size=dp(13))
        self.tb_sobre = ToggleButton(
            text="Sobrescribir", group="modo_wifi",
            background_normal="", background_down="",
            background_color=DANGER, color=TEXT, font_size=dp(13))
        modo_row.add_widget(self.tb_combinar)
        modo_row.add_widget(self.tb_sobre)
        self.body.add_widget(modo_row)

        # Botones principales
        self.body.add_widget(mk_btn(
            "ENVIAR a la PC (Android > PC)",
            lambda _: self._enviar(), bg=SUCCESS, height=dp(54)))

        self.body.add_widget(mk_btn(
            "RECIBIR de la PC (PC > Android)",
            lambda _: self._recibir(), bg=WARN, height=dp(54)))

        # Estado
        self.lbl_estado = Label(
            text="Sin conexión verificada",
            color=MUTED, font_size=dp(12),
            size_hint_y=None, height=dp(28))
        self.body.add_widget(self.lbl_estado)

        # Log
        self.body.add_widget(Label(text="Registro:",
                                    color=MUTED, font_size=dp(11),
                                    size_hint_y=None, height=dp(22)))
        scroll = ScrollView()
        self.log_box = GridLayout(cols=1, size_hint_y=None)
        self.log_box.bind(minimum_height=self.log_box.setter("height"))
        scroll.add_widget(self.log_box)
        self.body.add_widget(scroll)

    # ── Persistir IP ───────────────────────────────────────────────────────────
    def _ip_file(self):
        return os.path.join(dm.DATA_DIR, "servidor_ip.txt")

    def _cargar_ip_guardada(self):
        try:
            with open(self._ip_file(), 'r') as f:
                ip = f.read().strip()
                if ip:
                    self.inp_ip.text = ip
        except Exception:
            pass

    def _guardar_ip(self):
        try:
            with open(self._ip_file(), 'w') as f:
                f.write(self.inp_ip.text.strip())
            self._log("IP guardada OK")
        except Exception as e:
            self._log(f"Error guardando IP: {e}")

    # ── Helpers HTTP ───────────────────────────────────────────────────────────
    def _base_url(self):
        url = self.inp_ip.text.strip()
        if not url.startswith("http"):
            url = "http://" + url
        return url.rstrip("/")

    def _request(self, metodo, path, datos=None, timeout=10):
        """Realiza petición HTTP usando solo módulos builtin."""
        import urllib.request
        import urllib.error
        url = self._base_url() + path
        if metodo == "GET":
            req = urllib.request.Request(url)
        else:
            body = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            req  = urllib.request.Request(url, data=body,
                                           headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _request_csv(self, archivo, timeout=10):
        """Descarga un CSV del servidor."""
        import urllib.request
        url = self._base_url() + f"/descargar?archivo={archivo}"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    # ── Ping ───────────────────────────────────────────────────────────────────
    def _ping(self):
        self._guardar_ip()
        self._log("Verificando conexión...")
        self.lbl_estado.color = MUTED
        self.lbl_estado.text  = "Conectando..."

        def tarea():
            try:
                res = self._request("GET", "/ping")
                Clock.schedule_once(lambda _, r=res: self._ping_ok(r), 0)
            except Exception as e:
                err = str(e)
                Clock.schedule_once(lambda _, m=err: self._ping_error(m), 0)

        threading.Thread(target=tarea, daemon=True).start()

    def _ping_ok(self, res):
        self.lbl_estado.text  = "OK: conectado al servidor de la PC"
        self.lbl_estado.color = SUCCESS
        self._log(f"OK conexión - {res.get('mensaje','')}")

    def _ping_error(self, error):
        self.lbl_estado.text  = "Sin conexión con la PC"
        self.lbl_estado.color = DANGER
        self._log(f"Error: {error}")
        alerta("Sin conexión",
               "No se pudo conectar al servidor.\n\n"
               "Verifica:\n"
               "- El servidor está corriendo en la PC\n"
               "- Ambos dispositivos están en la misma WiFi\n"
               "- La IP es correcta")

    # ── Enviar Android → PC ────────────────────────────────────────────────────
    def _enviar(self):
        self._guardar_ip()
        modo = "combinar" if self.tb_combinar.state == "down" else "sobrescribir"
        self._log(f"Enviando datos a la PC (modo: {modo})...")
        self.lbl_estado.text  = "Enviando..."
        self.lbl_estado.color = MUTED

        def tarea():
            try:
                inv = dm.leer_inventario()
                ven = dm.leer_ventas()
                res = self._request("POST", "/sincronizar", {
                    "modo":       modo,
                    "inventario": inv,
                    "ventas":     ven
                })
                Clock.schedule_once(lambda _, r=res: self._enviar_ok(r), 0)
            except Exception as e:
                err = str(e)
                Clock.schedule_once(lambda _, m=err: self._enviar_error(m), 0)

        threading.Thread(target=tarea, daemon=True).start()

    def _enviar_ok(self, res):
        msg = (f"OK: datos enviados correctamente\n"
               f"Inventario en PC (cambios aplicados): {res.get('inv_nuevos', 0)}\n"
               f"Ventas nuevas en PC: {res.get('ven_nuevos', 0)}")
        self.lbl_estado.text  = "OK: enviado correctamente"
        self.lbl_estado.color = SUCCESS
        self._log(msg)
        # Refrescar todas las pantallas de datos (los CSV locales no cambian
        # al enviar, pero por consistencia se actualiza igual)
        self._refrescar_pantallas()
        alerta("Enviado", msg)

    def _enviar_error(self, error):
        self.lbl_estado.text  = "Error al enviar"
        self.lbl_estado.color = DANGER
        self._log(f"Error: {error}")
        alerta("Error al enviar", error)

    # ── Recibir PC → Android ───────────────────────────────────────────────────
    def _recibir(self):
        self._guardar_ip()
        self._log("Descargando datos de la PC...")
        self.lbl_estado.text  = "Descargando..."
        self.lbl_estado.color = MUTED

        def tarea():
            try:
                import csv, io
                inv_csv = self._request_csv("inventario")
                ven_csv = self._request_csv("ventas")

                inv_filas = list(csv.DictReader(io.StringIO(inv_csv)))
                ven_filas = list(csv.DictReader(io.StringIO(ven_csv)))

                st_inv = dm.fusionar_inventario_en_disco(inv_filas)
                st_ven = dm.fusionar_ventas_en_disco(ven_filas)
                ni = st_inv["nuevos"] + st_inv["actualizados_desde_remoto"]
                nv = st_ven["nuevas"]
                Clock.schedule_once(
                    lambda _, a=ni, b=nv: self._recibir_ok(a, b), 0)
            except Exception as e:
                err = str(e)
                Clock.schedule_once(lambda _, m=err: self._recibir_error(m), 0)

        threading.Thread(target=tarea, daemon=True).start()

    def _recibir_ok(self, inv_n, ven_n):
        msg = (f"OK: datos recibidos de la PC\n"
               f"Inventario (cambios aplicados): {inv_n}\n"
               f"Ventas nuevas: {ven_n}")
        self.lbl_estado.text  = "OK: recibido correctamente"
        self.lbl_estado.color = SUCCESS
        self._log(msg)
        # ── CORRECCIÓN: refrescar todas las pantallas con los datos nuevos ────
        self._refrescar_pantallas()
        alerta("Recibido", msg)

    def _recibir_error(self, error):
        self.lbl_estado.text  = "Error al recibir"
        self.lbl_estado.color = DANGER
        self._log(f"Error: {error}")
        alerta("Error al recibir", error)

    # ── NUEVO: refresca inventario, ventas y reportes sin navegar ─────────────
    def _refrescar_pantallas(self):
        """
        Recorre las pantallas de datos y llama a su método refresh().
        Se ejecuta siempre en el hilo principal (ya estamos en Clock callback).
        """
        for nombre in ("inventario", "ventas", "reportes"):
            try:
                self.manager.get_screen(nombre).refresh()
            except Exception:
                pass  # la pantalla aún no fue construida, se cargará al entrar

    def _log(self, texto):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.add_widget(
            Label(text=f"[color=#95a5a6][{ts}][/color] {texto}",
                  markup=True, color=TEXT, font_size=dp(11),
                  size_hint_y=None, height=dp(28), halign="left"))

# ══════════════════════════════════════════════════════════════════════════════
# APP PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
class InventarioApp(App):
    def build(self):
        dm.inicializar()
        sm = ScreenManager(transition=SlideTransition())
        sm.add_widget(MenuScreen(name="menu"))
        sm.add_widget(InventarioScreen(name="inventario"))
        sm.add_widget(VentasScreen(name="ventas"))
        sm.add_widget(ReportesScreen(name="reportes"))
        sm.add_widget(SyncScreen(name="sync"))
        return sm

if __name__ == "__main__":
    InventarioApp().run()
