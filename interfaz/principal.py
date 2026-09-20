import sys

from PySide6.QtWidgets import QApplication

from interfaz.configuracion import ConfiguracionInterfaz
from interfaz.ventana_principal_voz import VentanaPrincipal


def ejecutar() -> int:
    aplicacion = QApplication(sys.argv)
    ventana = VentanaPrincipal(ConfiguracionInterfaz())
    ventana.show()
    return aplicacion.exec()


if __name__ == "__main__":
    raise SystemExit(ejecutar())
