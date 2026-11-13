# Etapa 3.2: USB e encerramento de sessões

A entrada oficial é `python agente/agente.py`. O comando antigo
`python agente/agente_seguro.py` usa a mesma implementação, por compatibilidade.
Nenhuma transmissão de tela foi adicionada.

## Monitoramento e parada local

Cada sessão aceita cria sua própria segurança. A presença e o conteúdo da
credencial USB são verificados localmente a cada 250 ms, sem esperar a rede.
Outro monitor verifica a credencial no servidor, com intervalo de um segundo
entre verificações. A confirmação da sessão continua usando o fluxo de atividade.
As verificações e o encerramento HTTP executam fora da thread do Tkinter.

Cada execução do monitor possui um evento de cancelamento independente.
Resultados antigos são descartados por sessão e por geração. Reconectar o USB
não desbloqueia uma sessão interrompida: é necessária uma nova solicitação aceita.

O botão visível interrompe a captura antes de agendar o encerramento remoto.
Quando uma falha é detectada, a autorização local é bloqueada e a captura
também verifica esse bloqueio antes de cada frame. A interface processa os
eventos de segurança a cada 200 ms. Fechar apenas a prévia continua permitindo
reabri-la enquanto a sessão permanecer autorizada e monitorada.

Esses intervalos não são garantias de tempo real: detecção depende do Windows,
do acesso ao dispositivo e do escalonamento das threads. Revogação e falha de
rede só podem ser reconhecidas após a resposta ou falha da verificação HTTP
(timeout configurado de cinco segundos). A captura para assim que o bloqueio
é observado; não depende da confirmação do encerramento no servidor.

## Autorização exclusiva de encerramento

Ao criar uma sessão aceita, o servidor entrega ao Agente um segredo aleatório
exclusivo para `POST /sessoes/encerrar-autorizado`. A autorização está vinculada
ao identificador da sessão e ao computador e vence cinco minutos depois do
prazo máximo original da sessão (oito horas).

O servidor guarda somente seu hash. O Agente guarda a autorização em memória,
sem precisar reler o pendrive para encerrar. Consultas, atividade e respostas de
encerramento não retornam o segredo nem seus metadados internos.

O primeiro uso consome a autorização. Repetições válidas apenas confirmam o
estado final, para suportar perda de resposta; nunca reativam a sessão. A mesma
autorização não autentica consultas, atividade, WebSocket ou novas conexões.
Na falha de rede, o Agente mantém a autorização para uma nova tentativa pelo
botão de encerramento e mantém a captura bloqueada.

Sessões antigas não recebem retroativamente essa autorização: o fluxo antigo
permanece disponível e a supervisão por inatividade cobre a desconexão.

## Supervisão no servidor

O ciclo de vida do FastAPI inicia uma supervisão com intervalo de um segundo,
executando acesso aos arquivos fora do loop assíncrono. Ela verifica expiração,
30 segundos sem atividade, credencial revogada, ausência de computador agente
e perda do consentimento registrado ou divergência das permissões. A revogação
pela API também aciona a supervisão imediatamente.

Sem rede, não é possível entregar uma notificação instantânea ao servidor.
Nesse caso, o Agente para localmente e a supervisão encerra por inatividade.
Falhas de leitura da autorização bloqueiam as sessões por segurança. Uma falha
que impeça gravar o arquivo de sessões é registrada sem credenciais e a tarefa
tenta novamente no próximo ciclo.

O armazenamento continua sendo JSON com bloqueios dentro de um processo;
esta etapa não adiciona suporte a múltiplos workers do servidor.

## Testes

Execute na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Os testes usam diretórios temporários, computadores e credenciais fictícios,
mocks da interface/USB/rede e servidores locais em portas temporárias.
Os hashes dos arquivos reais são comparados antes e depois da suíte. A proteção
adicionada na etapa 3.5 bloqueia gravações nos dados reais pelo processo de testes;
alterações de outros aplicativos já abertos são reportadas separadamente.
Não é necessário interromper nenhum servidor existente. Nenhum token é impresso.
Os testes de interface não substituem uma validação manual com Tkinter e um
pendrive físico no Windows.
