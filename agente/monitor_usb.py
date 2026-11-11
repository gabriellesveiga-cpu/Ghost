import threading
from typing import Callable


class MonitorUSB:
    def __init__(
        self,
        verificar_usb: Callable[[], bool],
        ao_remover: Callable[[], None],
        intervalo: float = 0.5
    ):
        self.verificar_usb = verificar_usb
        self.ao_remover = ao_remover
        self.intervalo = intervalo

        self._parar = threading.Event()
        self._thread = None

    def iniciar(self):
        if self._thread and self._thread.is_alive():
            return

        self._parar.clear()

        self._thread = threading.Thread(
            target=self._executar,
            daemon=True
        )

        self._thread.start()

    def _executar(self):
        while not self._parar.is_set():
            try:
                usb_presente = (
                    self.verificar_usb() is True
                )
            except Exception:
                usb_presente = False

            if not usb_presente:
                self._parar.set()
                self.ao_remover()
                return

            if self._parar.wait(self.intervalo):
                return

    def parar(self):
        self._parar.set()
