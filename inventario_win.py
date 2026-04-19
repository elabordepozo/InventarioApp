"""
inventario_win.py — Aplicación de escritorio Windows
Requiere: Python 3.8+ (Tkinter incluido)
Uso: python inventario_win.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import sys, os, json, socket, threading, subprocess
import http.server
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_manager as dm

# ── Puerto del servidor WiFi ───────────────────────────────────────────────────
PUERTO_SYNC = 8765

# ── Paleta de colores ──────────────────────────────────────────────────────────
C = {
    "bg":       "#1e2b38",
    "panel":    "#253545",
    "card":     "#2d4059",
    "accent":   "#3498db",
    "success":  "#27ae60",
    "danger":   "#e74c3c",
    "warn":     "#f39c12",
    "text":     "#ecf0f1",
    "muted":    "#95a5a6",
    "entry_bg": "#1a2530",
    "entry_fg": "#ecf0f1",
    "sel":      "#3d566e",
}

def btn(parent, text, cmd, color=None, **kw):
    color = color or C["accent"]
    b = tk.Button(parent, text=text, command=cmd,
                  bg=color, fg="white", activebackground=color,
                  activeforeground="white", relief="flat", bd=0,
                  padx=12, pady=6, cursor="hand2",
                  font=("Segoe UI", 9, "bold"), **kw)
    b.bind("<Enter>", lambda e: b.config(bg=_lighten(color)))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    return b

def _lighten(hex_color):
    r, g, b = int(hex_color[1:3],16), int(hex_color[3:5],16), int(hex_color[5:7],16)
    return "#{:02x}{:02x}{:02x}".format(min(r+30,255), min(g+30,255), min(b+30,255))

def lbl(parent, text, size=9, bold=False, color=None, **kw):
    font = ("Segoe UI", size, "bold" if bold else "normal")
    return tk.Label(parent, text=text, font=font,
                    bg=kw.pop("bg", C["panel"]),
                    fg=color or C["text"], **kw)

def entry(parent, textvariable=None, width=20, **kw):
    return tk.Entry(parent, textvariable=textvariable, width=width,
                    bg=C["entry_bg"], fg=C["entry_fg"],
                    insertbackground=C["text"], relief="flat",
                    highlightbackground=C["accent"], highlightthickness=1,
                    font=("Segoe UI", 9), **kw)

# ── Helpers WiFi ───────────────────────────────────────────────────────────────
def get_todas_las_ips():
    """Devuelve lista de (ip, nombre_adaptador) disponibles en esta PC."""
    ips = {}
    try:
        result = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, encoding="cp850"
        )
        adaptador = "Desconocido"
        for linea in result.stdout.splitlines():
            stripped = linea.strip()
            if stripped and not linea.startswith(" ") and ":" in stripped:
                adaptador = stripped.rstrip(":")
            if "IPv4" in stripped and ":" in stripped:
                ip = stripped.split(":")[-1].strip()
                if ip and ip != "127.0.0.1" and ":" not in ip:
                    ips[ip] = adaptador
    except Exception:
        pass
    if not ips:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None):
                ip = info[4][0]
                if ":" not in ip and ip != "127.0.0.1":
                    ips[ip] = "Adaptador de red"
        except Exception:
            pass
    return list(ips.items()) or [("127.0.0.1", "Loopback")]

def _combinar_csv(archivo, campos, nuevas):
    """Fusiona filas remotas: inventario por updated_at; ventas por id nuevo."""
    if archivo == dm.INVENTARIO_FILE:
        st = dm.fusionar_inventario_en_disco(nuevas)
        return st["nuevos"] + st["actualizados_desde_remoto"]
    st = dm.fusionar_ventas_en_disco(nuevas)
    return st["nuevas"]

# ── Handler HTTP para sincronización WiFi ─────────────────────────────────────
class _SyncHandler(http.server.BaseHTTPRequestHandler):

    # Callbacks inyectados desde App al iniciar el servidor
    log_callback     = None   # fn(str) → escribe en el log de la UI
    refresh_callback = None   # fn()    → recarga tablas de inventario y ventas

    def log_message(self, format, *args):
        msg = f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}"
        if _SyncHandler.log_callback:
            _SyncHandler.log_callback(msg)

    def _json(self, codigo, datos):
        body = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)

        if parsed.path == "/ping":
            self._json(200, {"ok": True, "mensaje": "Servidor activo ✔"})

        elif parsed.path == "/descargar":
            params  = parse_qs(parsed.query)
            nombre  = params.get("archivo", [""])[0]
            archivo = dm.INVENTARIO_FILE if nombre == "inventario" else \
                      dm.VENTAS_FILE     if nombre == "ventas"     else None
            if not archivo or not os.path.exists(archivo):
                self._json(404, {"error": "Archivo no encontrado"})
                return
            with open(archivo, 'r', encoding='utf-8') as f:
                contenido = f.read()
            body = contenido.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json(404, {"error": "Ruta no encontrada"})

    def do_POST(self):
        if self.path != "/sincronizar":
            self._json(404, {"error": "Ruta no encontrada"})
            return
        try:
            longitud = int(self.headers.get("Content-Length", 0))
            datos    = json.loads(self.rfile.read(longitud).decode("utf-8"))
            modo     = datos.get("modo", "combinar")
            inv      = datos.get("inventario", [])
            ven      = datos.get("ventas",     [])

            if modo == "sobrescribir":
                dm.guardar_inventario_sobrescribir(inv)
                dm._guardar_csv_generico(dm.VENTAS_FILE, dm.VENTAS_FIELDS, ven)
                inv_n, ven_n = len(inv), len(ven)
            else:
                inv_n = _combinar_csv(dm.INVENTARIO_FILE, dm.INVENTARIO_FIELDS, inv)
                ven_n = _combinar_csv(dm.VENTAS_FILE,     dm.VENTAS_FIELDS,     ven)

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            msg = (f"✔ Sync recibida [{ts}]  "
                   f"Inventario (nuevos o actualizados): {inv_n}  "
                   f"Ventas nuevas: {ven_n}")
            if _SyncHandler.log_callback:
                _SyncHandler.log_callback(msg)

            # ── CORRECCIÓN: refrescar la UI de Windows tras recibir datos ─────
            if _SyncHandler.refresh_callback:
                _SyncHandler.refresh_callback()

            self._json(200, {"ok": True, "inv_nuevos": inv_n,
                             "ven_nuevos": ven_n, "mensaje": "✔ Sincronizado"})
        except Exception as e:
            if _SyncHandler.log_callback:
                _SyncHandler.log_callback(f"✘ Error en POST: {e}")
            self._json(500, {"ok": False, "error": str(e)})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# ── Aplicación principal ───────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        dm.inicializar()
        self.title("📦 Control de Inventario y Ventas")
        self.geometry("960x680")
        self.minsize(800, 580)
        self.configure(bg=C["bg"])
        self._servidor_wifi = None
        self._estilo_ttk()
        self._header()
        self._tabs()
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    # ── Cierre seguro ─────────────────────────────────────────────────────────
    def _al_cerrar(self):
        if self._servidor_wifi:
            self._servidor_wifi.shutdown()
        self.destroy()

    # ── CORRECCIÓN: recarga todas las tablas desde disco ─────────────────────
    def _refrescar_todo(self):
        """
        Llamado por _SyncHandler.refresh_callback después de cada sync WiFi.
        Se programa con self.after() para ejecutarse en el hilo principal de Tkinter.
        """
        self._cargar_inventario()
        self._cargar_ventas_hoy()
        # Si el reporte de hoy está visible, actualizarlo también
        try:
            self._render_reporte(dm.ventas_hoy())
        except Exception:
            pass

    # ── Estilo ttk ────────────────────────────────────────────────────────────
    def _estilo_ttk(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TNotebook",          background=C["bg"],  borderwidth=0)
        s.configure("TNotebook.Tab",      background=C["panel"], foreground=C["muted"],
                    padding=[14, 6], font=("Segoe UI", 9, "bold"))
        s.map("TNotebook.Tab",
              background=[("selected", C["accent"])],
              foreground=[("selected", "white")])
        s.configure("Treeview",           background=C["card"], foreground=C["text"],
                    fieldbackground=C["card"], rowheight=26, font=("Segoe UI", 9))
        s.configure("Treeview.Heading",   background=C["panel"], foreground=C["accent"],
                    font=("Segoe UI", 9, "bold"), relief="flat")
        s.map("Treeview", background=[("selected", C["accent"])],
              foreground=[("selected", "white")])
        s.configure("TScrollbar",         background=C["panel"], troughcolor=C["bg"],
                    arrowcolor=C["muted"])
        s.configure("Horizontal.TSeparator", background=C["accent"])

    # ── Header ────────────────────────────────────────────────────────────────
    def _header(self):
        f = tk.Frame(self, bg="#141e2a", pady=8)
        f.pack(fill="x")
        lbl(f, "📦  Control de Inventario y Ventas", size=13, bold=True,
            bg="#141e2a").pack(side="left", padx=16)
        self._lbl_hora = lbl(f, "", size=9, bg="#141e2a", color=C["muted"])
        self._lbl_hora.pack(side="right", padx=16)
        self._tick()

    def _tick(self):
        self._lbl_hora.config(text=datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
        self.after(1000, self._tick)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    def _tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(4,8))
        self.nb = nb

        tabs = [
            ("📦  Inventario",  self._tab_inventario),
            ("💰  Ventas",      self._tab_ventas),
            ("📊  Reportes",    self._tab_reportes),
            ("🔄  Sincronizar", self._tab_sync),
        ]
        for titulo, constructor in tabs:
            frame = tk.Frame(nb, bg=C["panel"])
            nb.add(frame, text=titulo)
            constructor(frame)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB: INVENTARIO
    # ══════════════════════════════════════════════════════════════════════════
    def _tab_inventario(self, parent):
        top = tk.Frame(parent, bg=C["panel"], pady=6)
        top.pack(fill="x", padx=10)
        lbl(top, "Buscar:", bg=C["panel"]).pack(side="left")
        self._var_buscar = tk.StringVar()
        self._var_buscar.trace_add("write", lambda *_: self._filtrar_inventario())
        entry(top, textvariable=self._var_buscar, width=28).pack(side="left", padx=6)
        btn(top, "＋ Agregar Producto", self._dlg_agregar).pack(side="right", padx=4)

        cols = ("ID", "Nombre", "Código", "Precio", "Stock")
        frame_tree = tk.Frame(parent, bg=C["panel"])
        frame_tree.pack(fill="both", expand=True, padx=10, pady=(0,4))

        self.tree_inv = ttk.Treeview(frame_tree, columns=cols, show="headings",
                                      selectmode="browse")
        widths = [70, 250, 140, 90, 80]
        for col, w in zip(cols, widths):
            self.tree_inv.heading(col, text=col)
            self.tree_inv.column(col, width=w, anchor="center" if w < 200 else "w")

        sb = ttk.Scrollbar(frame_tree, orient="vertical",
                           command=self.tree_inv.yview)
        self.tree_inv.configure(yscrollcommand=sb.set)
        self.tree_inv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        bot = tk.Frame(parent, bg=C["panel"], pady=6)
        bot.pack(fill="x", padx=10)
        btn(bot, "✏  Editar",   self._dlg_editar,   color=C["warn"]).pack(side="left", padx=4)
        btn(bot, "🗑  Eliminar", self._eliminar_prod, color=C["danger"]).pack(side="left", padx=4)
        btn(bot, "↺  Actualizar", self._cargar_inventario).pack(side="right", padx=4)

        self._cargar_inventario()

    def _cargar_inventario(self, productos=None):
        if productos is None:
            productos = dm.leer_inventario()
        self.tree_inv.delete(*self.tree_inv.get_children())
        for p in productos:
            stock = int(p["stock"])
            tag = "low" if stock <= 5 else ""
            self.tree_inv.insert("", "end", iid=p["id"],
                                  values=(p["id"], p["nombre"], p["codigo"],
                                          f"$ {float(p['precio']):.2f}", stock),
                                  tags=(tag,))
        self.tree_inv.tag_configure("low", foreground=C["warn"])

    def _filtrar_inventario(self):
        txt = self._var_buscar.get().strip()
        if txt:
            self._cargar_inventario(dm.buscar_por_nombre(txt))
        else:
            self._cargar_inventario()

    def _sel_producto(self):
        sel = self.tree_inv.selection()
        if not sel:
            messagebox.showwarning("Atención", "Selecciona un producto primero.")
            return None
        pid = sel[0]
        prods = {p["id"]: p for p in dm.leer_inventario()}
        return prods.get(pid)

    def _dlg_agregar(self):
        self._dlg_producto()

    def _dlg_editar(self):
        p = self._sel_producto()
        if p:
            self._dlg_producto(p)

    def _dlg_producto(self, producto=None):
        dlg = tk.Toplevel(self)
        dlg.title("Editar Producto" if producto else "Nuevo Producto")
        dlg.geometry("380x280")
        dlg.configure(bg=C["card"])
        dlg.resizable(False, False)
        dlg.grab_set()

        campos = ["Nombre", "Código / QR", "Precio (CUP)", "Stock"]
        vars_ = [tk.StringVar() for _ in campos]

        if producto:
            vars_[0].set(producto["nombre"])
            vars_[1].set(producto["codigo"])
            vars_[2].set(producto["precio"])
            vars_[3].set(producto["stock"])

        form = tk.Frame(dlg, bg=C["card"], padx=20, pady=15)
        form.pack(fill="both", expand=True)

        for i, (campo, var) in enumerate(zip(campos, vars_)):
            lbl(form, campo + ":", bg=C["card"]).grid(row=i, column=0,
                sticky="e", pady=6, padx=(0,8))
            entry(form, textvariable=var, width=24).grid(row=i, column=1,
                sticky="ew", pady=6)

        form.columnconfigure(1, weight=1)

        def guardar():
            nombre, codigo, precio, stock = [v.get().strip() for v in vars_]
            if not nombre:
                messagebox.showerror("Error", "El nombre es obligatorio.", parent=dlg)
                return
            try:
                precio = float(precio or 0)
                stock  = int(stock   or 0)
            except ValueError:
                messagebox.showerror("Error", "Precio y Stock deben ser números.", parent=dlg)
                return
            if producto:
                dm.editar_producto(producto["id"], nombre, codigo, precio, stock)
            else:
                dm.agregar_producto(nombre, codigo, precio, stock)
            self._cargar_inventario()
            dlg.destroy()

        bot = tk.Frame(dlg, bg=C["card"], pady=8)
        bot.pack(fill="x", padx=20)
        btn(bot, "💾 Guardar", guardar, color=C["success"]).pack(side="right", padx=4)
        btn(bot, "Cancelar", dlg.destroy, color=C["muted"]).pack(side="right", padx=4)

    def _eliminar_prod(self):
        p = self._sel_producto()
        if not p:
            return
        if messagebox.askyesno("Confirmar",
                               f"¿Eliminar '{p['nombre']}'?\nEsta acción no se puede deshacer."):
            dm.eliminar_producto(p["id"])
            self._cargar_inventario()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB: VENTAS
    # ══════════════════════════════════════════════════════════════════════════
    def _tab_ventas(self, parent):
        form = tk.LabelFrame(parent, text="  Nueva Venta  ",
                             bg=C["card"], fg=C["accent"],
                             font=("Segoe UI", 10, "bold"), pady=10, padx=14)
        form.pack(fill="x", padx=14, pady=10)

        r1 = tk.Frame(form, bg=C["card"])
        r1.pack(fill="x", pady=4)
        lbl(r1, "Buscar producto:", bg=C["card"]).pack(side="left")
        self._var_buscar_v = tk.StringVar()
        entry(r1, textvariable=self._var_buscar_v, width=28).pack(side="left", padx=6)
        btn(r1, "🔍 Buscar", self._buscar_prod_venta).pack(side="left", padx=4)

        lbl(r1, "  o Código:", bg=C["card"]).pack(side="left", padx=(10,0))
        self._var_cod_v = tk.StringVar()
        e_cod = entry(r1, textvariable=self._var_cod_v, width=14)
        e_cod.pack(side="left", padx=6)
        e_cod.bind("<Return>", lambda _: self._buscar_por_cod_venta())
        btn(r1, "↵", self._buscar_por_cod_venta).pack(side="left")

        r2 = tk.Frame(form, bg=C["card"])
        r2.pack(fill="x", pady=4)
        lbl(r2, "Producto:", bg=C["card"]).pack(side="left")
        self._combo_prod = ttk.Combobox(r2, width=34, state="readonly",
                                        font=("Segoe UI", 9))
        self._combo_prod.pack(side="left", padx=6)
        self._combo_prod.bind("<<ComboboxSelected>>", self._al_seleccionar_prod)

        self._lbl_precio_v = lbl(r2, "Precio: —", bg=C["card"], color=C["accent"])
        self._lbl_precio_v.pack(side="left", padx=16)
        self._lbl_stock_v  = lbl(r2, "Stock: —", bg=C["card"], color=C["muted"])
        self._lbl_stock_v.pack(side="left")

        r3 = tk.Frame(form, bg=C["card"])
        r3.pack(fill="x", pady=4)
        lbl(r3, "Cantidad:", bg=C["card"]).pack(side="left")
        self._var_cant = tk.StringVar(value="1")
        entry(r3, textvariable=self._var_cant, width=8).pack(side="left", padx=6)
        btn(r3, "✔  Registrar Venta", self._registrar_venta,
            color=C["success"]).pack(side="left", padx=14)

        self._prod_actual = None

        lbl(parent, "  Ventas de hoy:", bg=C["panel"], bold=True).pack(
            anchor="w", padx=14, pady=(6,2))

        cols = ("Hora", "Producto", "Cant.", "P.Unit", "Total")
        frame_tv = tk.Frame(parent, bg=C["panel"])
        frame_tv.pack(fill="both", expand=True, padx=14, pady=(0,8))

        self.tree_ven = ttk.Treeview(frame_tv, columns=cols, show="headings",
                                      height=8, selectmode="none")
        widths_v = [100, 260, 60, 90, 90]
        for col, w in zip(cols, widths_v):
            self.tree_ven.heading(col, text=col)
            self.tree_ven.column(col, width=w,
                                  anchor="center" if w < 150 else "w")
        sb2 = ttk.Scrollbar(frame_tv, orient="vertical",
                            command=self.tree_ven.yview)
        self.tree_ven.configure(yscrollcommand=sb2.set)
        self.tree_ven.pack(side="left", fill="both", expand=True)
        sb2.pack(side="right", fill="y")

        self._cargar_ventas_hoy()

    def _buscar_prod_venta(self):
        txt = self._var_buscar_v.get().strip()
        prods = dm.buscar_por_nombre(txt) if txt else dm.leer_inventario()
        self._prods_venta = prods
        self._combo_prod["values"] = [f"{p['nombre']}  (Stock: {p['stock']})"
                                       for p in prods]
        if prods:
            self._combo_prod.current(0)
            self._al_seleccionar_prod()

    def _buscar_por_cod_venta(self):
        cod = self._var_cod_v.get().strip()
        p = dm.buscar_por_codigo(cod)
        if p:
            self._prods_venta = [p]
            self._combo_prod["values"] = [f"{p['nombre']}  (Stock: {p['stock']})"]
            self._combo_prod.current(0)
            self._al_seleccionar_prod()
        else:
            messagebox.showwarning("No encontrado", f"No hay producto con código: {cod}")

    def _al_seleccionar_prod(self, *_):
        idx = self._combo_prod.current()
        if idx >= 0 and hasattr(self, "_prods_venta") and self._prods_venta:
            self._prod_actual = self._prods_venta[idx]
            p = self._prod_actual
            self._lbl_precio_v.config(text=f"Precio: $ {float(p['precio']):.2f}")
            self._lbl_stock_v.config(text=f"Stock: {p['stock']}")

    def _registrar_venta(self):
        if not self._prod_actual:
            messagebox.showwarning("Atención", "Selecciona un producto.")
            return
        try:
            cant = int(self._var_cant.get())
            if cant <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Cantidad debe ser un entero positivo.")
            return

        ok, resultado = dm.registrar_venta(
            self._prod_actual["id"], self._prod_actual["nombre"],
            cant, self._prod_actual["precio"]
        )
        if ok:
            total = float(resultado["total"])
            messagebox.showinfo("Venta registrada",
                                f"✔ Venta exitosa\n"
                                f"Producto : {resultado['producto_nombre']}\n"
                                f"Cantidad : {cant}\n"
                                f"Total    : $ {total:.2f}")
            self._cargar_ventas_hoy()
            self._cargar_inventario()
            self._var_cant.set("1")
            self._prod_actual = None
            self._combo_prod.set("")
            self._lbl_precio_v.config(text="Precio: —")
            self._lbl_stock_v.config(text="Stock: —")
        else:
            messagebox.showerror("Error", resultado)

    def _cargar_ventas_hoy(self):
        self.tree_ven.delete(*self.tree_ven.get_children())
        for v in dm.ventas_hoy():
            hora = v["fecha"].split(" ")[-1][:5]
            self.tree_ven.insert("", "end", values=(
                hora, v["producto_nombre"], v["cantidad"],
                f"$ {float(v['precio_unit']):.2f}",
                f"$ {float(v['total']):.2f}"
            ))

    # ══════════════════════════════════════════════════════════════════════════
    # TAB: REPORTES
    # ══════════════════════════════════════════════════════════════════════════
    def _tab_reportes(self, parent):
        top = tk.Frame(parent, bg=C["panel"], pady=8)
        top.pack(fill="x", padx=14)
        lbl(top, "Año:", bg=C["panel"]).pack(side="left")
        self._var_anio = tk.StringVar(value=str(datetime.now().year))
        entry(top, textvariable=self._var_anio, width=6).pack(side="left", padx=4)
        lbl(top, "Mes:", bg=C["panel"]).pack(side="left", padx=(10,0))
        meses = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                 "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
        self._combo_mes = ttk.Combobox(top, values=meses, width=12, state="readonly")
        self._combo_mes.current(datetime.now().month - 1)
        self._combo_mes.pack(side="left", padx=4)
        btn(top, "📊 Ver Reporte", self._mostrar_reporte).pack(side="left", padx=14)
        btn(top, "Hoy", self._reporte_hoy, color=C["warn"]).pack(side="left")

        self._frame_resumen = tk.Frame(parent, bg=C["card"], pady=10)
        self._frame_resumen.pack(fill="x", padx=14, pady=6)
        self._lbls_resumen = {}
        datos = [("Ventas", "num_ventas"), ("Ítems vendidos", "items_vendidos"),
                 ("Total ingresos", "total_ingresos")]
        for i, (titulo, key) in enumerate(datos):
            col = tk.Frame(self._frame_resumen, bg=C["card"])
            col.pack(side="left", expand=True, fill="x")
            lbl(col, titulo, size=9, bg=C["card"], color=C["muted"]).pack()
            v = lbl(col, "—", size=16, bold=True, bg=C["card"], color=C["accent"])
            v.pack()
            self._lbls_resumen[key] = v

        cols = ("Fecha", "Producto", "Cant.", "P.Unit", "Total")
        frame_r = tk.Frame(parent, bg=C["panel"])
        frame_r.pack(fill="both", expand=True, padx=14, pady=(0,8))
        self.tree_rep = ttk.Treeview(frame_r, columns=cols, show="headings",
                                      selectmode="none")
        widths_r = [140, 240, 60, 90, 90]
        for col, w in zip(cols, widths_r):
            self.tree_rep.heading(col, text=col)
            self.tree_rep.column(col, width=w,
                                  anchor="center" if w < 150 else "w")
        sb3 = ttk.Scrollbar(frame_r, orient="vertical",
                            command=self.tree_rep.yview)
        self.tree_rep.configure(yscrollcommand=sb3.set)
        self.tree_rep.pack(side="left", fill="both", expand=True)
        sb3.pack(side="right", fill="y")

        self._mostrar_reporte()

    def _mostrar_reporte(self):
        try:
            anio = int(self._var_anio.get())
            mes  = self._combo_mes.current() + 1
        except ValueError:
            messagebox.showerror("Error", "Año inválido.")
            return
        self._render_reporte(dm.ventas_mes(anio, mes))

    def _reporte_hoy(self):
        self._render_reporte(dm.ventas_hoy())

    def _render_reporte(self, ventas):
        res = dm.resumen(ventas)
        self._lbls_resumen["num_ventas"].config(text=str(res["num_ventas"]))
        self._lbls_resumen["items_vendidos"].config(text=str(res["items_vendidos"]))
        self._lbls_resumen["total_ingresos"].config(
            text=f"$ {res['total_ingresos']:.2f}")

        self.tree_rep.delete(*self.tree_rep.get_children())
        for v in ventas:
            self.tree_rep.insert("", "end", values=(
                v["fecha"][:16], v["producto_nombre"],
                v["cantidad"],   f"$ {float(v['precio_unit']):.2f}",
                f"$ {float(v['total']):.2f}"
            ))

    # ══════════════════════════════════════════════════════════════════════════
    # TAB: SINCRONIZAR  (USB + Servidor WiFi integrado)
    # ══════════════════════════════════════════════════════════════════════════
    def _tab_sync(self, parent):
        nb_inner = ttk.Notebook(parent)
        nb_inner.pack(fill="both", expand=True, padx=6, pady=6)

        f_usb  = tk.Frame(nb_inner, bg=C["panel"])
        f_wifi = tk.Frame(nb_inner, bg=C["panel"])
        nb_inner.add(f_usb,  text="💾  USB / Archivos")
        nb_inner.add(f_wifi, text="📡  Servidor WiFi")

        self._build_usb_tab(f_usb)
        self._build_wifi_tab(f_wifi)

    # ── Sub-pestaña USB ────────────────────────────────────────────────────────
    def _build_usb_tab(self, parent):
        sec_exp = tk.LabelFrame(parent, text="  📤 Exportar (este dispositivo → USB)  ",
                                bg=C["card"], fg=C["success"],
                                font=("Segoe UI", 10, "bold"), pady=10, padx=14)
        sec_exp.pack(fill="x", padx=14, pady=10)

        r = tk.Frame(sec_exp, bg=C["card"])
        r.pack(fill="x")
        lbl(r, "Directorio destino:", bg=C["card"]).pack(side="left")
        self._var_exp_dir = tk.StringVar()
        entry(r, textvariable=self._var_exp_dir, width=38).pack(side="left", padx=6)
        btn(r, "📁 Examinar", lambda: self._elegir_dir(self._var_exp_dir)).pack(side="left")
        btn(sec_exp, "📤 EXPORTAR CSV", self._exportar, color=C["success"]).pack(pady=8)

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=14, pady=4)

        sec_imp = tk.LabelFrame(parent, text="  📥 Importar (USB → este dispositivo)  ",
                                bg=C["card"], fg=C["warn"],
                                font=("Segoe UI", 10, "bold"), pady=10, padx=14)
        sec_imp.pack(fill="x", padx=14, pady=10)

        r2 = tk.Frame(sec_imp, bg=C["card"])
        r2.pack(fill="x")
        lbl(r2, "Directorio origen:", bg=C["card"]).pack(side="left")
        self._var_imp_dir = tk.StringVar()
        entry(r2, textvariable=self._var_imp_dir, width=38).pack(side="left", padx=6)
        btn(r2, "📁 Examinar", lambda: self._elegir_dir(self._var_imp_dir)).pack(side="left")

        r3 = tk.Frame(sec_imp, bg=C["card"])
        r3.pack(fill="x", pady=6)
        lbl(r3, "Modo:", bg=C["card"]).pack(side="left")
        self._var_modo_usb = tk.StringVar(value="combinar")
        tk.Radiobutton(r3, text="Combinar (recomendado)", variable=self._var_modo_usb,
                       value="combinar", bg=C["card"], fg=C["text"],
                       selectcolor=C["bg"], activebackground=C["card"],
                       font=("Segoe UI", 9)).pack(side="left", padx=8)
        tk.Radiobutton(r3, text="Sobrescribir", variable=self._var_modo_usb,
                       value="sobrescribir", bg=C["card"], fg=C["danger"],
                       selectcolor=C["bg"], activebackground=C["card"],
                       font=("Segoe UI", 9)).pack(side="left")

        btn(sec_imp, "📥 IMPORTAR CSV", self._importar, color=C["warn"]).pack(pady=8)

        lbl(parent, "  Registro:", bg=C["panel"], bold=True).pack(
            anchor="w", padx=14, pady=(4, 0))
        self._log_usb_widget = scrolledtext.ScrolledText(
            parent, height=5, bg=C["entry_bg"], fg=C["text"],
            font=("Consolas", 9), relief="flat", state="disabled", wrap="word")
        self._log_usb_widget.pack(fill="both", expand=True, padx=14, pady=(0,8))
        self._log_usb("Listo para sincronizar por USB.")

    # ── Sub-pestaña WiFi ───────────────────────────────────────────────────────
    def _build_wifi_tab(self, parent):
        sel_frame = tk.LabelFrame(parent,
                                  text="  🌐 Adaptador de red (conecta el teléfono a esta misma WiFi)  ",
                                  bg=C["card"], fg=C["accent"],
                                  font=("Segoe UI", 10, "bold"), pady=10, padx=14)
        sel_frame.pack(fill="x", padx=14, pady=(10, 4))

        todas_ips = get_todas_las_ips()
        opciones  = [f"{ip}   —   {nombre}" for ip, nombre in todas_ips]

        self._var_ip_wifi = tk.StringVar(value=opciones[0] if opciones else "")
        self._combo_ip = ttk.Combobox(sel_frame, textvariable=self._var_ip_wifi,
                                      values=opciones, state="readonly", width=58,
                                      font=("Segoe UI", 9))
        self._combo_ip.pack(fill="x", pady=(4, 0))

        for i, (ip, nombre) in enumerate(todas_ips):
            n = nombre.lower()
            if "wi-fi" in n or "wifi" in n or "inalámbric" in n or \
               "wireless" in n or ip.startswith("192.168") or ip.startswith("10."):
                self._combo_ip.current(i)
                break

        info_frame = tk.Frame(parent, bg=C["panel"], pady=8, padx=16)
        info_frame.pack(fill="x", padx=14, pady=(0, 6))
        lbl(info_frame, "Dirección para ingresar en el Android:",
            bg=C["panel"], color=C["muted"]).pack(anchor="w")
        self._lbl_url_wifi = tk.Label(info_frame, text="—",
                                       font=("Consolas", 15, "bold"),
                                       bg=C["panel"], fg=C["success"])
        self._lbl_url_wifi.pack(anchor="w")
        self._var_ip_wifi.trace_add("write", self._actualizar_url_wifi)
        self._actualizar_url_wifi()

        estado_f = tk.Frame(parent, bg=C["panel"], pady=4, padx=16)
        estado_f.pack(fill="x", padx=14)
        self._lbl_estado_wifi = tk.Label(
            estado_f, text="⏸  Servidor detenido",
            font=("Segoe UI", 10, "bold"), bg=C["panel"], fg=C["muted"])
        self._lbl_estado_wifi.pack(side="left")

        bts = tk.Frame(parent, bg=C["panel"], pady=6)
        bts.pack(fill="x", padx=14)
        self._btn_iniciar_wifi = btn(bts, "▶  Iniciar Servidor",
                                      self._iniciar_servidor_wifi, color=C["success"])
        self._btn_iniciar_wifi.pack(side="left", padx=4)
        self._btn_detener_wifi = btn(bts, "⏹  Detener",
                                      self._detener_servidor_wifi, color=C["danger"])
        self._btn_detener_wifi.pack(side="left", padx=4)
        self._btn_detener_wifi.config(state="disabled")

        lbl(parent, "  Registro de actividad:", bg=C["panel"], bold=True).pack(
            anchor="w", padx=14, pady=(4, 0))
        self._log_wifi_widget = scrolledtext.ScrolledText(
            parent, height=7, bg=C["entry_bg"], fg=C["text"],
            font=("Consolas", 9), relief="flat", state="disabled", wrap="word")
        self._log_wifi_widget.pack(fill="both", expand=True, padx=14, pady=(0,8))
        self._log_wifi("Servidor WiFi listo. Selecciona el adaptador e inicia.")

    # ── Control del servidor WiFi ─────────────────────────────────────────────
    def _actualizar_url_wifi(self, *_):
        sel = self._var_ip_wifi.get()
        ip  = sel.split("   —   ")[0].strip() if sel else "—"
        self._lbl_url_wifi.config(text=f"http://{ip}:{PUERTO_SYNC}")

    def _iniciar_servidor_wifi(self):
        sel = self._var_ip_wifi.get()
        ip  = sel.split("   —   ")[0].strip()
        try:
            # Inyectar ambos callbacks en el handler
            _SyncHandler.log_callback     = lambda msg: self.after(0, self._log_wifi, msg)
            # ── CORRECCIÓN: after() garantiza ejecución en el hilo de Tkinter ──
            _SyncHandler.refresh_callback = lambda: self.after(0, self._refrescar_todo)

            self._servidor_wifi = http.server.HTTPServer((ip, PUERTO_SYNC), _SyncHandler)
            threading.Thread(target=self._servidor_wifi.serve_forever,
                             daemon=True).start()

            self._lbl_estado_wifi.config(
                text="▶  Servidor activo — esperando Android...", fg=C["success"])
            self._btn_iniciar_wifi.config(state="disabled")
            self._btn_detener_wifi.config(state="normal")
            self._combo_ip.config(state="disabled")
            self._log_wifi(f"✔ Servidor iniciado en http://{ip}:{PUERTO_SYNC}")
            self._log_wifi("→ Ingresa esa dirección en la app Android.")
        except Exception as e:
            self._lbl_estado_wifi.config(text=f"✘ Error: {e}", fg=C["danger"])
            self._log_wifi(f"✘ Error al iniciar: {e}")

    def _detener_servidor_wifi(self):
        if self._servidor_wifi:
            threading.Thread(target=self._servidor_wifi.shutdown,
                             daemon=True).start()
            self._servidor_wifi = None
        _SyncHandler.refresh_callback = None
        self._lbl_estado_wifi.config(text="⏸  Servidor detenido", fg=C["muted"])
        self._btn_iniciar_wifi.config(state="normal")
        self._btn_detener_wifi.config(state="disabled")
        self._combo_ip.config(state="readonly")
        self._log_wifi("⏸ Servidor detenido.")

    # ── Logs ──────────────────────────────────────────────────────────────────
    def _log_wifi(self, texto):
        self._escribir_log(self._log_wifi_widget, texto)

    def _log_usb(self, texto):
        self._escribir_log(self._log_usb_widget, texto)

    @staticmethod
    def _escribir_log(widget, texto):
        widget.configure(state="normal")
        ts = datetime.now().strftime("%H:%M:%S")
        widget.insert("end", f"[{ts}] {texto}\n")
        widget.see("end")
        widget.configure(state="disabled")

    # ── USB helpers ───────────────────────────────────────────────────────────
    def _elegir_dir(self, var):
        d = filedialog.askdirectory(title="Selecciona directorio")
        if d:
            var.set(d)

    def _exportar(self):
        destino = self._var_exp_dir.get().strip()
        if not destino:
            messagebox.showwarning("Atención", "Selecciona el directorio destino.")
            return
        res = dm.exportar_a(destino)
        self._log_usb(f"✔ Exportado → {destino}  |  "
                      f"Productos: {res['inventario']}  Ventas: {res['ventas']}")
        messagebox.showinfo("Exportado",
                            f"CSV exportados a:\n{destino}\n\n"
                            f"Copia esa carpeta al otro dispositivo.")

    def _importar(self):
        origen = self._var_imp_dir.get().strip()
        if not origen:
            messagebox.showwarning("Atención", "Selecciona el directorio origen.")
            return
        modo = self._var_modo_usb.get()
        if modo == "sobrescribir":
            if not messagebox.askyesno(
                    "¿Sobrescribir?",
                    "Se reemplazarán TODOS los datos locales.\n¿Continuar?"):
                return
        res = dm.importar_de(origen, modo)
        msg = (f"✔ Importación completada (modo: {modo})\n"
               f"   Productos nuevos : {res['inventario_nuevos']}\n"
               f"   Ventas nuevas    : {res['ventas_nuevas']}")
        if res["errores"]:
            msg += f"\n   Errores : {', '.join(res['errores'])}"
        self._log_usb(msg)
        messagebox.showinfo("Importado", msg)
        self._cargar_inventario()
        self._cargar_ventas_hoy()


# ── Punto de entrada ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
