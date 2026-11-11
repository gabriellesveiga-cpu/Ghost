from monitor_usb import MonitorUSB
from validar_usb import validar_usb_servidor


class SegurancaCompartilhamento:
    def __init__(self, ao_interromper):
        self.ao_interromper = ao_interromper

        self.monitor = MonitorUSB(
            verificar_usb=self.verificar_usb,
            ao_remover=self.interromper,
            intervalo=0.5
        )

    def verificar_usb(self):
        try:
            resultado = validar_usb_servidor()

            return (
                isinstance(resultado, dict)
                and resultado.get("valida") is True
            )

        except Exception:
            return False

    def iniciar(self):
        if not self.verificar_usb():
            self.interromper()
            return False

        self.monitor.iniciar()
        return True

    def interromper(self):
        self.monitor.parar()
        self.ao_interromper()

    def parar(self):
        self.monitor.parar()
