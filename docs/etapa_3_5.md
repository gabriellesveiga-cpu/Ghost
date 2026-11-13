# Etapa 3.5: criação e recuperação de sessões

## Operações repetidas e falhas de persistência

O par computador/solicitação identifica a operação. Repetir a mesma decisão é
permitido; trocar aceite por recusa ou recusa por aceite é rejeitado. Solicitações
pendentes, recusadas, canceladas ou expiradas não criam sessões.

O aceite e a sessão continuam em arquivos JSON separados. Não há uma transação
atômica entre os dois arquivos. O fluxo permite concluir cada etapa após falhas:

1. Falha antes de salvar o aceite: permanece pendente; repetir pode registrar a
   mesma decisão explícita.
2. Aceite salvo, sessão ainda não salva: repetir conclui a criação dentro do prazo.
3. Sessão salva e resposta perdida: repetir retorna a mesma sessão ativa.

Bloqueios com ordem consistente serializam consulta, validação e gravação dentro
do processo do servidor. O fluxo respeita a regra de uma sessão ativa por
computador. Não há suporte a múltiplos processos escrevendo nos mesmos JSON.

Repetições não renovam a duração da sessão, a última atividade ou o prazo do
consentimento. Sessões encerradas nunca voltam ao estado ativo; tentar iniciá-las
novamente retorna conflito e exige uma nova solicitação aceita.

## Prazo do aceite ainda não utilizado

O primeiro uso deve ocorrer em até dois minutos após o aceite. O horário fica em
`autorizacao_expira_em`. Para registros anteriores sem esse campo, considera-se
`respondida_em` mais dois minutos; datas ausentes ou inválidas impedem a criação.

Esse prazo não encerra uma sessão que já foi criada. O status histórico da
solicitação permanece `aceita`, mesmo se seu prazo de primeiro uso já terminou.

## Recuperação autenticada

`POST /sessoes/recuperar` recebe o identificador da solicitação e as credenciais
normais do Agente (computador, chave e segredo USB). A resposta mantém os dados
da solicitação e informa a sessão correspondente ou `null` se o aceite ainda não
gerou uma sessão. A recuperação não registra aceite nem cria sessões.

A consulta exige uma solicitação aceita e pertencente ao computador autenticado.
As permissões são verificadas contra o consentimento salvo. Sessões terminadas
podem ser identificadas, mas são devolvidas sem autorização de encerramento e não
são adotadas pelo Agente como sessões ativas.

Para sessões novas criadas pela API, a autorização exclusiva de encerramento é
derivada por HMAC, com domínio próprio, a partir das credenciais autenticadas e
do identificador da sessão. Assim o servidor pode reentregar a mesma autorização
após uma resposta perdida ou reinício, sem salvar o segredo em texto puro.
A validade original, o consumo e o escopo exclusivo de encerramento permanecem.

Sessões anteriores a esta etapa conservam suas autorizações aleatórias originais.
Se esse segredo antigo tiver sido perdido, a recuperação informa a identificação,
mas não o reproduz. Permanecem o encerramento autenticado com USB e a supervisão
por inatividade; nenhuma migração dos dados reais é feita nesta etapa.

## Agente e segurança local

O envio da decisão usa no máximo duas tentativas de resposta. Após timeout,
queda de conexão, falha transitória do servidor ou resposta JSON inválida, um
aceite tenta recuperar a sessão pela solicitação original. Se o aceite não chegou,
a mesma decisão pode ser reenviada. A recuperação não solicita novas permissões.

Cada nova tentativa relê a identidade e o pendrive; remoção, mudança de credencial
ou rejeição de autenticação interrompe a operação. O monitor da etapa 3.2 e os
identificadores de sessão/geração continuam impedindo que eventos atrasados
reativem a captura. Todas as chamadas permanecem no worker, fora do Tkinter.

Uma queda prolongada pode esgotar as tentativas e gerar erro na interface. Não há
retomada automática de sessões após reiniciar o Agente ou reconectar o pendrive.
O servidor encerra sessões sem atividade; uma sessão já encerrada exige novo
consentimento. O encerramento visível e a prévia local não foram removidos.

## Testes

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Os testes usam persistência temporária, credenciais fictícias e servidores em
portas livres. Um audit hook bloqueia escrita, substituição e remoção dos dados
reais pelo processo de testes. Os hashes também são conferidos; mudanças feitas
por aplicativos já abertos são reportadas separadamente e não são revertidas.

São cobertos concorrência, respostas perdidas antes/depois de gravar, nova
instância lendo o estado persistido, falhas de rede, prazos, vínculos,
revogação/remoção USB, encerramento e compatibilidade das respostas da API.
Nenhuma transmissão de tela foi adicionada.
