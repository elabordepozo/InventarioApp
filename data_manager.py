"""
data_manager.py — Lógica compartida para Windows y Android
Maneja inventario.csv y ventas.csv
"""

import csv
import os
import uuid
from datetime import datetime

# ── Rutas de archivos ──────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
INVENTARIO_FILE = os.path.join(DATA_DIR, "inventario.csv")
VENTAS_FILE     = os.path.join(DATA_DIR, "ventas.csv")

# updated_at: última modificación del registro (sincronización gana el más reciente)
INVENTARIO_FIELDS = ["id", "nombre", "codigo", "precio", "stock", "updated_at"]
VENTAS_FIELDS     = ["id", "fecha", "producto_id", "producto_nombre",
                     "cantidad", "precio_unit", "total"]

STAMP_FMT = "%Y-%m-%d %H:%M:%S"
_TS_MIN = datetime(2000, 1, 1, 0, 0, 0)


def _ahora_str():
    return datetime.now().strftime(STAMP_FMT)


def _parse_ts(s):
    if not s or not str(s).strip():
        return _TS_MIN
    try:
        return datetime.strptime(str(s).strip()[:19], STAMP_FMT)
    except ValueError:
        return _TS_MIN


def normalizar_fila_inventario(p):
    """Garantiza todas las claves de INVENTARIO_FIELDS; updated_at vacío = antiguo."""
    d = {}
    for k in INVENTARIO_FIELDS:
        v = p.get(k, "")
        if v is None:
            v = ""
        d[k] = str(v).strip()
    if not d.get("updated_at"):
        d["updated_at"] = "2000-01-01 00:00:00"
    return d


def _fusionar_inventario_por_fecha(locales, remotas):
    """
    Por cada id, conserva la fila con updated_at más reciente.
    Empate → gana remoto (último en enviar / última sincronización).
    Devuelve (lista fusionada, estadísticas).
    """
    by_id = {}
    for p in locales:
        pid = p.get("id")
        if pid:
            by_id[pid] = normalizar_fila_inventario(p)
    stats = {"nuevos": 0, "actualizados_desde_remoto": 0, "sin_cambio": 0}
    for r in remotas:
        rid = r.get("id")
        if not rid:
            continue
        r = normalizar_fila_inventario(r)
        if rid not in by_id:
            by_id[rid] = dict(r)
            stats["nuevos"] += 1
            continue
        l = by_id[rid]
        tl, tr = _parse_ts(l.get("updated_at")), _parse_ts(r.get("updated_at"))
        if tr > tl:
            by_id[rid] = dict(r)
            stats["actualizados_desde_remoto"] += 1
        elif tr < tl:
            stats["sin_cambio"] += 1
        else:
            by_id[rid] = dict(r)
            stats["actualizados_desde_remoto"] += 1
    return list(by_id.values()), stats


def fusionar_inventario_en_disco(filas_remotas):
    """Fusiona inventario recibido de otro dispositivo sobre el CSV local."""
    locales = leer_inventario()
    merged, stats = _fusionar_inventario_por_fecha(locales, filas_remotas)
    _guardar_inventario(merged)
    return stats


def fusionar_ventas_en_disco(filas_remotas):
    """Añade ventas cuyo id no exista localmente (mismo criterio que antes)."""
    locales = leer_ventas()
    ids_local = {v["id"] for v in locales if v.get("id")}
    nuevas = [dict(v) for v in filas_remotas if v.get("id") and v["id"] not in ids_local]
    if not nuevas:
        return {"nuevas": 0}
    todas = locales + nuevas
    with open(VENTAS_FILE, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=VENTAS_FIELDS)
        w.writeheader()
        w.writerows(todas)
    return {"nuevas": len(nuevas)}


def guardar_inventario_sobrescribir(filas):
    """Reemplaza inventario local; marca todo con la misma hora (última fuente explícita)."""
    ts = _ahora_str()
    rows = [normalizar_fila_inventario(dict(p)) for p in filas]
    for r in rows:
        r["updated_at"] = ts
    _guardar_inventario(rows)

# ── Inicialización ─────────────────────────────────────────────────────────────
def inicializar():
    """Crea el directorio y los CSV si no existen."""
    os.makedirs(DATA_DIR, exist_ok=True)
    for archivo, campos in [(INVENTARIO_FILE, INVENTARIO_FIELDS),
                            (VENTAS_FILE,     VENTAS_FIELDS)]:
        if not os.path.exists(archivo):
            with open(archivo, 'w', newline='', encoding='utf-8') as f:
                csv.DictWriter(f, fieldnames=campos).writeheader()

# ── Helpers CSV genéricos (usados por el servidor WiFi integrado) ──────────────
def _leer_csv_generico(archivo):
    """Lee cualquier CSV y devuelve lista de dicts."""
    if not os.path.exists(archivo):
        return []
    with open(archivo, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def _guardar_csv_generico(archivo, campos, filas):
    """Escribe una lista de dicts en el CSV indicado."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(archivo, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

# ── INVENTARIO ─────────────────────────────────────────────────────────────────
def leer_inventario():
    inicializar()
    with open(INVENTARIO_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if "updated_at" not in fieldnames:
        rows = [normalizar_fila_inventario(dict(r)) for r in rows]
        if rows:
            ts = _ahora_str()
            for r in rows:
                r["updated_at"] = ts
            _guardar_inventario(rows)
        return rows
    return [normalizar_fila_inventario(dict(r)) for r in rows]

def _guardar_inventario(productos):
    limpios = [normalizar_fila_inventario(p) for p in productos]
    with open(INVENTARIO_FILE, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=INVENTARIO_FIELDS)
        w.writeheader()
        w.writerows(limpios)

def agregar_producto(nombre, codigo, precio, stock):
    productos = leer_inventario()
    nuevo = {
        "id":     str(uuid.uuid4())[:8].upper(),
        "nombre": nombre.strip(),
        "codigo": codigo.strip(),
        "precio": str(float(precio)),
        "stock":  str(int(stock)),
        "updated_at": _ahora_str(),
    }
    productos.append(nuevo)
    _guardar_inventario(productos)
    return nuevo

def editar_producto(prod_id, nombre, codigo, precio, stock):
    productos = leer_inventario()
    for p in productos:
        if p["id"] == prod_id:
            p.update({"nombre": nombre.strip(), "codigo": codigo.strip(),
                      "precio": str(float(precio)), "stock": str(int(stock)),
                      "updated_at": _ahora_str()})
            break
    _guardar_inventario(productos)

def eliminar_producto(prod_id):
    _guardar_inventario([p for p in leer_inventario() if p["id"] != prod_id])

def buscar_por_codigo(codigo):
    return next((p for p in leer_inventario() if p["codigo"] == codigo), None)

def buscar_por_nombre(texto):
    texto = texto.lower()
    return [p for p in leer_inventario() if texto in p["nombre"].lower()]

# ── VENTAS ─────────────────────────────────────────────────────────────────────
def leer_ventas():
    inicializar()
    with open(VENTAS_FILE, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def registrar_venta(producto_id, producto_nombre, cantidad, precio_unit):
    cantidad   = int(cantidad)
    precio_unit = float(precio_unit)

    productos = leer_inventario()
    actualizado = False
    for p in productos:
        if p["id"] == producto_id:
            stock_actual = int(p["stock"])
            if stock_actual < cantidad:
                return False, f"Stock insuficiente (disponible: {stock_actual})"
            p["stock"] = str(stock_actual - cantidad)
            p["updated_at"] = _ahora_str()
            actualizado = True
            break
    if not actualizado:
        return False, "Producto no encontrado"
    _guardar_inventario(productos)

    venta = {
        "id":               str(uuid.uuid4())[:8].upper(),
        "fecha":            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "producto_id":      producto_id,
        "producto_nombre":  producto_nombre,
        "cantidad":         str(cantidad),
        "precio_unit":      str(precio_unit),
        "total":            str(round(cantidad * precio_unit, 2))
    }
    ventas = leer_ventas()
    ventas.append(venta)
    with open(VENTAS_FILE, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=VENTAS_FIELDS)
        w.writeheader()
        w.writerows(ventas)
    return True, venta

# ── REPORTES ───────────────────────────────────────────────────────────────────
def ventas_hoy():
    hoy = datetime.now().strftime("%Y-%m-%d")
    return [v for v in leer_ventas() if v["fecha"].startswith(hoy)]

def ventas_mes(anio=None, mes=None):
    if anio is None: anio = datetime.now().year
    if mes  is None: mes  = datetime.now().month
    prefijo = f"{anio}-{mes:02d}"
    return [v for v in leer_ventas() if v["fecha"].startswith(prefijo)]

def resumen(ventas):
    total = sum(float(v["total"])  for v in ventas)
    items = sum(int(v["cantidad"]) for v in ventas)
    return {"num_ventas": len(ventas), "items_vendidos": items,
            "total_ingresos": round(total, 2)}

# ── SINCRONIZACIÓN USB ─────────────────────────────────────────────────────────
def exportar_a(destino_dir):
    """Copia los CSV al directorio destino (USB/transferencia)."""
    import shutil
    os.makedirs(destino_dir, exist_ok=True)
    shutil.copy2(INVENTARIO_FILE, os.path.join(destino_dir, "inventario.csv"))
    shutil.copy2(VENTAS_FILE,     os.path.join(destino_dir, "ventas.csv"))
    return {"inventario": len(leer_inventario()), "ventas": len(leer_ventas())}

def importar_de(origen_dir, modo="combinar"):
    """
    Importa CSV desde un directorio de origen.
    modo='combinar': fusiona sin duplicar (usa ID único)
    modo='sobrescribir': reemplaza los datos locales
    """
    import shutil
    resultados = {"inventario_nuevos": 0, "ventas_nuevas": 0, "errores": []}

    inv_src = os.path.join(origen_dir, "inventario.csv")
    ven_src = os.path.join(origen_dir, "ventas.csv")

    if not os.path.exists(inv_src) and not os.path.exists(ven_src):
        resultados["errores"].append("No se encontraron archivos CSV en el directorio.")
        return resultados

    if os.path.exists(inv_src):
        if modo == "sobrescribir":
            with open(inv_src, 'r', encoding='utf-8') as f:
                remotas = list(csv.DictReader(f))
            remotas = [normalizar_fila_inventario(dict(p)) for p in remotas]
            for p in remotas:
                if _parse_ts(p.get("updated_at")) <= _TS_MIN:
                    p["updated_at"] = _ahora_str()
            _guardar_inventario(remotas)
            resultados["inventario_nuevos"] = len(remotas)
        else:
            with open(inv_src, 'r', encoding='utf-8') as f:
                remotas = list(csv.DictReader(f))
            st = fusionar_inventario_en_disco(remotas)
            resultados["inventario_nuevos"] = (
                st["nuevos"] + st["actualizados_desde_remoto"])

    if os.path.exists(ven_src):
        if modo == "sobrescribir":
            shutil.copy2(ven_src, VENTAS_FILE)
            resultados["ventas_nuevas"] = len(leer_ventas())
        else:
            with open(ven_src, 'r', encoding='utf-8') as f:
                remotas_v = list(csv.DictReader(f))
            stv = fusionar_ventas_en_disco(remotas_v)
            resultados["ventas_nuevas"] = stv["nuevas"]

    return resultados
