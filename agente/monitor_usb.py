import threading
from typing import Callable


class MonitorUSB:
    """Cada execução tem cancelamento próprio, inclusive durante I/O."""

    def __init__(self, verificar_usb: Callable[[], bool],
                 ao_remover: Callable[[], None], intervalo: float = 0.5):
        self.verificar_usb = verificar_usb
        self.ao_remover = ao_remover
        self.intervalo = intervalo
        self._lock = threading.RLock()
        self._parar = threading.Event()
        self._thread = None

    def iniciar(self):
        with self._lock:
            if self._thread and self._thread.is_alive() and not self._parar.is_set():
                return
            cancelamento = threading.Event()
            self._parar = cancelamento
            self._thread = threading.Thread(
                target=self._executar, args=(cancelamento,), daemon=True
            )
            self._thread.start()

    def _executar(self, cancelamento):
        while not cancelamento.is_set():
            try:
                presente = self.verificar_usb() is True
            except Exception:
                presente = False
            with self._lock:
                if cancelamento.is_set() or cancelamento is not self._parar:
                    return
                if not presente:
                    cancelamento.set()
                    # Callback curto (fila), serializado com parar/reiniciar.
                    self.ao_remover()
                    return
            if cancelamento.wait(self.intervalo):
                return

    def parar(self):
        # Não espera por rede na thread do Tkinter.
        with self._lock:
            self._parar.set()
