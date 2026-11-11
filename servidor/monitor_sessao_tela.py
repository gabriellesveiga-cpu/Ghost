
from .autorizacao_tela import verificar_autorizacao_tela


class MonitorSessaoTela:

    def __init__(self, sessao_id, computador_id):
        self.sessao_id = sessao_id
        self.computador_id = computador_id
        self.interrompido = False

    def verificar(self):
        if self.interrompido:
            return {
                "autorizado": False,
                "motivo": "Monitoramento interrompido."
            }

        try:
            resultado = verificar_autorizacao_tela(
                self.sessao_id,
                self.computador_id
            )
        except Exception:
            self.interrompido = True
            return {
                "autorizado": False,
                "motivo": "Falha na verificacao da sessao."
            }

        if not resultado.get("autorizado"):
            self.interrompido = True

        return resultado

    def interromper(self):
        self.interrompido = True
