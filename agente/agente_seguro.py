
import tkinter as tk
from queue import Queue, Empty

from agente import KeyNexusAgente
from seguranca_compartilhamento import SegurancaCompartilhamento


class KeyNexusAgenteSeguro(KeyNexusAgente):

    def __init__(self, janela):
        self.eventos_seguranca = Queue()
        self.seguranca_usb = None
        self.usb_interrompido = False

        super().__init__(janela)

        self.janela.after(
            100,
            self.processar_eventos_seguranca
        )

    def avisar_perda_usb(self):
        # Executado pela thread de monitoramento.
        # Nenhuma interface Tkinter e alterada aqui.
        self.eventos_seguranca.put("usb_invalido")

    def abrir_captura(self):
        if not self.captura_autorizada():
            return

        if self.seguranca_usb is None:
            self.seguranca_usb = SegurancaCompartilhamento(
                ao_interromper=self.avisar_perda_usb
            )

        # Verifica o USB real antes de abrir a captura.
        if not self.seguranca_usb.iniciar():
            self.suspender_sessao(
                "Credencial USB indisponivel."
            )
            return

        super().abrir_captura()

    def interromper_captura(self):
        if self.seguranca_usb is not None:
            self.seguranca_usb.parar()

        super().interromper_captura()

    def processar_eventos_seguranca(self):
        if not self.ativo:
            return

        try:
            while True:
                evento = self.eventos_seguranca.get_nowait()

                if evento == "usb_invalido":
                    if not self.usb_interrompido:
                        self.usb_interrompido = True

                        self.suspender_sessao(
                            "Pendrive removido ou credencial invalida."
                        )

                        if self.sessao_atual is not None:
                            self.solicitar_encerramento()

        except Empty:
            pass

        self.janela.after(
            100,
            self.processar_eventos_seguranca
        )

    def fechar(self):
        if self.seguranca_usb is not None:
            self.seguranca_usb.parar()

        super().fechar()


if __name__ == "__main__":
    janela = tk.Tk()
    KeyNexusAgenteSeguro(janela)
    janela.mainloop()
