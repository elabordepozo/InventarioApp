# Punto de entrada para APK (Buildozer / python-for-android)

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy_garden.zbarcam import ZBarCam

# Importa tu app original
from inventario_kivy_wifi import InventarioApp


class Scanner(ZBarCam):
    def on_symbols(self, instance, symbols):
        if symbols:
            codigo = symbols[0].data.decode("utf-8")
            print("Código detectado:", codigo)

            # Aquí puedes integrar con tu lógica de inventario
            # Ejemplo:
            # InventarioApp.buscar_producto(codigo)


class MainApp(App):
    def build(self):
        layout = BoxLayout(orientation="vertical")

        # Inicializa tu app original
        self.inventario = InventarioApp()

        # Scanner
        scanner = Scanner()
        layout.add_widget(scanner)

        return layout


if __name__ == "__main__":
    MainApp().run()
