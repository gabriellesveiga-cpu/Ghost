import threading

from monitor_usb import MonitorUSB
from solicitacoes import obter_autenticacao
from validar_usb import validar_usb_servidor


class SegurancaCompartilhamento:
    """Uma instância por sessão; a perda de autorização é definitiva."""

    def __init__(self, ao_interromper):
        self.ao_interromper = ao_interromper
        self._lock = threading.RLock()
        self._credencial = None
        self._bloqueado = threading.Event()
        self._local_validado = threading.Event()
        self._servidor_validado = threading.Event()
        self.monitor = MonitorUSB(self.verificar_local, self.interromper, 0.25)
        self.monitor_servidor = MonitorUSB(self.verificar_usb, self.interromper, 1)

    def verificar_local(self):
        if self._bloqueado.is_set():
            return False
        autenticacao = obter_autenticacao()
        with self._lock:
            if self._credencial is None:
                self._credencial = autenticacao
            if autenticacao != self._credencial:
                return False
            self._local_validado.set()
        return True

    def verificar_usb(self):
        if self._bloqueado.is_set():
            return False
        resultado = validar_usb_servidor()
        valido = isinstance(resultado, dict) and resultado.get("valida") is True
        if valido:
            self._servidor_validado.set()
        return valido

    def autorizada(self):
        return (not self._bloqueado.is_set()
                and self._local_validado.is_set()
                and self._servidor_validado.is_set())

    def iniciar(self):
        if self._bloqueado.is_set():
            return False
        self.monitor.iniciar()
        self.monitor_servidor.iniciar()
        return True

    def interromper(self):
        with self._lock:
            if self._bloqueado.is_set():
                return
            self._bloqueado.set()
        # Não adquire o lock do outro monitor dentro de um callback.
        # O guard já bloqueou a captura; a UI cancela ambos ao ler a fila.
        self.ao_interromper()

    def parar(self):
        self._bloqueado.set()
        self.monitor.parar()
        self.monitor_servidor.parar()
