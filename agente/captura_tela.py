
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import mss
import time


class CapturaTela:
    def __init__(self, janela, sessao_id=None, pode_capturar=None):
        self.janela = janela
        self.sessao_id = sessao_id
        self.pode_capturar = pode_capturar
        self.janela.title("KeyNexus — Captura de Tela")
        self.janela.geometry("1000x720")
        self.janela.minsize(700, 550)
        self.janela.configure(bg="#0D0B12")

        self.capturando = False
        self.capturador = None
        self.imagem_atual = None
        self.tarefa_atualizacao = None

        self.monitor_selecionado = tk.StringVar(value="1")
        self.qualidade = tk.StringVar(value="Média")

        self.total_frames = 0
        self.inicio_fps = time.monotonic()

        self.criar_interface()
        self.carregar_monitores()

        self.janela.protocol(
            "WM_DELETE_WINDOW",
            self.fechar
        )

    def criar_interface(self):
        tk.Label(
            self.janela,
            text="KEYNEXUS",
            font=("Segoe UI", 25, "bold"),
            fg="#B78CFF",
            bg="#0D0B12"
        ).pack(pady=(15, 3))

        tk.Label(
            self.janela,
            text="Pré-visualização local de tela",
            font=("Segoe UI", 11),
            fg="#B9B0C6",
            bg="#0D0B12"
        ).pack()

        configuracoes = tk.Frame(
            self.janela,
            bg="#191522"
        )
        configuracoes.pack(
            fill="x",
            padx=20,
            pady=15
        )

        tk.Label(
            configuracoes,
            text="Monitor:",
            bg="#191522",
            fg="white"
        ).pack(side="left", padx=(15, 5), pady=12)

        self.combo_monitor = ttk.Combobox(
            configuracoes,
            textvariable=self.monitor_selecionado,
            state="readonly",
            width=8
        )
        self.combo_monitor.pack(side="left", padx=5)

        tk.Label(
            configuracoes,
            text="Qualidade:",
            bg="#191522",
            fg="white"
        ).pack(side="left", padx=(25, 5))

        self.combo_qualidade = ttk.Combobox(
            configuracoes,
            textvariable=self.qualidade,
            values=["Baixa", "Média", "Alta"],
            state="readonly",
            width=12
        )
        self.combo_qualidade.pack(side="left", padx=5)

        self.status = tk.Label(
            self.janela,
            text="● Captura desativada",
            font=("Segoe UI", 11, "bold"),
            fg="#FFB86B",
            bg="#0D0B12"
        )
        self.status.pack(pady=5)

        self.area_imagem = tk.Label(
            self.janela,
            text="Clique em Iniciar captura",
            font=("Segoe UI", 12),
            fg="#B9B0C6",
            bg="#191522"
        )
        self.area_imagem.pack(
            padx=20,
            pady=10,
            fill="both",
            expand=True
        )

        self.info_fps = tk.Label(
            self.janela,
            text="FPS: 0 | Resolução: —",
            font=("Segoe UI", 10),
            fg="#B9B0C6",
            bg="#0D0B12"
        )
        self.info_fps.pack(pady=5)

        botoes = tk.Frame(
            self.janela,
            bg="#0D0B12"
        )
        botoes.pack(pady=15)

        self.botao_iniciar = tk.Button(
            botoes,
            text="Iniciar captura",
            font=("Segoe UI", 11, "bold"),
            bg="#6D42A8",
            fg="white",
            relief="flat",
            padx=20,
            pady=10,
            command=self.iniciar
        )
        self.botao_iniciar.pack(side="left", padx=10)

        self.botao_parar = tk.Button(
            botoes,
            text="Parar captura",
            font=("Segoe UI", 11, "bold"),
            bg="#A83E58",
            fg="white",
            relief="flat",
            padx=20,
            pady=10,
            state="disabled",
            command=self.parar
        )
        self.botao_parar.pack(side="left", padx=10)

        tk.Label(
            self.janela,
            text="Pré-visualização local — nenhuma imagem é transmitida.",
            font=("Segoe UI", 9),
            fg="#8D839C",
            bg="#0D0B12"
        ).pack(pady=(0, 10))

    def carregar_monitores(self):
        try:
            with mss.mss() as captura:
                quantidade = len(captura.monitors) - 1

            valores = [
                str(numero)
                for numero in range(1, quantidade + 1)
            ]

            self.combo_monitor["values"] = valores

            if valores:
                self.monitor_selecionado.set(valores[0])

        except Exception as erro:
            messagebox.showerror(
                "Erro",
                f"Não foi possível listar monitores:\n{erro}"
            )

    def iniciar(self):
        if self.pode_capturar is not None and not self.pode_capturar():
            return
        if self.capturando:
            return

        try:
            self.capturador = mss.mss()

            indice = int(self.monitor_selecionado.get())

            if indice >= len(self.capturador.monitors):
                raise ValueError("Monitor inválido.")

            self.capturando = True
            self.total_frames = 0
            self.inicio_fps = time.monotonic()

            self.combo_monitor.config(state="disabled")
            self.combo_qualidade.config(state="disabled")
            self.botao_iniciar.config(state="disabled")
            self.botao_parar.config(state="normal")

            self.status.config(
                text="● Captura local ativa",
                fg="#7ED9A3"
            )

            self.atualizar_tela()

        except Exception as erro:
            self.parar()

            messagebox.showerror(
                "Erro na captura",
                str(erro)
            )

    def atualizar_tela(self):
        self.tarefa_atualizacao = None

        if self.pode_capturar is not None and not self.pode_capturar():
            self.parar()
            return

        if not self.capturando:
            return

        try:
            indice = int(self.monitor_selecionado.get())
            monitor = self.capturador.monitors[indice]

            captura = self.capturador.grab(monitor)

            imagem = Image.frombytes(
                "RGB",
                captura.size,
                captura.rgb
            )

            resolucao_original = imagem.size

            fatores = {
                "Baixa": 0.35,
                "Média": 0.60,
                "Alta": 1.0
            }

            fator = fatores[self.qualidade.get()]

            largura_qualidade = max(
                1,
                int(imagem.width * fator)
            )
            altura_qualidade = max(
                1,
                int(imagem.height * fator)
            )

            imagem = imagem.resize(
                (largura_qualidade, altura_qualidade),
                Image.Resampling.LANCZOS
            )

            largura_area = max(
                self.area_imagem.winfo_width() - 20,
                320
            )
            altura_area = max(
                self.area_imagem.winfo_height() - 20,
                240
            )

            imagem.thumbnail(
                (largura_area, altura_area),
                Image.Resampling.LANCZOS
            )

            self.imagem_atual = ImageTk.PhotoImage(imagem)

            self.area_imagem.config(
                image=self.imagem_atual,
                text=""
            )

            self.total_frames += 1
            tempo = time.monotonic() - self.inicio_fps

            if tempo >= 1:
                fps = self.total_frames / tempo

                self.info_fps.config(
                    text=(
                        f"FPS: {fps:.1f} | "
                        f"Resolução: "
                        f"{resolucao_original[0]}x"
                        f"{resolucao_original[1]}"
                    )
                )

                self.total_frames = 0
                self.inicio_fps = time.monotonic()

            self.tarefa_atualizacao = self.janela.after(
                100,
                self.atualizar_tela
            )

        except Exception as erro:
            self.parar()

            messagebox.showerror(
                "Erro na captura",
                str(erro)
            )

    def parar(self):
        self.capturando = False

        if self.tarefa_atualizacao is not None:
            self.janela.after_cancel(
                self.tarefa_atualizacao
            )
            self.tarefa_atualizacao = None

        if self.capturador is not None:
            self.capturador.close()
            self.capturador = None

        self.imagem_atual = None

        self.area_imagem.config(
            image="",
            text="Captura interrompida"
        )

        self.status.config(
            text="● Captura desativada",
            fg="#FFB86B"
        )

        self.info_fps.config(
            text="FPS: 0 | Resolução: —"
        )

        self.combo_monitor.config(state="readonly")
        self.combo_qualidade.config(state="readonly")
        self.botao_iniciar.config(state="normal")
        self.botao_parar.config(state="disabled")

    def fechar(self):
        self.parar()
        self.janela.destroy()


if __name__ == "__main__":
    janela = tk.Tk()
    CapturaTela(janela)
    janela.mainloop()
