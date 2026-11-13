"""Limites em memória por origem; nenhum usuário, token ou segredo é armazenado."""
from collections import deque
import hashlib
import math
import threading
from time import monotonic


class LimiteTentativas:
    def __init__(self, max_falhas, max_tentativas, janela=60, max_origens=1024,
                 relogio=monotonic):
        self.max_falhas = max_falhas
        self.max_tentativas = max_tentativas
        self.janela = janela
        self.max_origens = max_origens
        self.relogio = relogio
        self._origens = {}
        self._lock = threading.Lock()

    def _limpar(self, registro, agora):
        for fila in registro:
            while fila and fila[0] <= agora - self.janela:
                fila.popleft()

    def admitir(self, origem):
        chave = hashlib.sha256(origem.encode()).digest()
        with self._lock:
            agora = self.relogio()
            registro = self._origens.get(chave)
            if registro is None:
                for antiga, filas in list(self._origens.items()):
                    self._limpar(filas, agora)
                    if not any(filas):
                        self._origens.pop(antiga)
                if len(self._origens) >= self.max_origens:
                    return self.janela
                registro = (deque(), deque())
                self._origens[chave] = registro
            self._limpar(registro, agora)
            tentativas, falhas = registro
            for fila, limite in ((tentativas, self.max_tentativas), (falhas, self.max_falhas)):
                if len(fila) >= limite:
                    return max(1, math.ceil(fila[0] + self.janela - agora))
            tentativas.append(agora)
            return 0

    def falha(self, origem):
        chave = hashlib.sha256(origem.encode()).digest()
        with self._lock:
            registro = self._origens.get(chave)
            if registro is not None:
                self._limpar(registro, self.relogio())
                # Limita também a memória sob falhas simultâneas.
                if len(registro[1]) < self.max_falhas:
                    registro[1].append(self.relogio())
