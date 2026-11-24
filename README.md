# PRESIQ — piloto de check-in TotalPass

O painel compartilhado do professor fica em `/professor` e atualiza a cada cinco segundos. A tela original em `/` continua sendo uma demonstração local. Para o piloto, o painel usa a relação de reservas em `turmas.json`, independente das reservas da demonstração. O Wellhub ainda não está integrado.

## Teste local

1. Instale as dependências com `python -m pip install -r requirements.txt`.
2. Execute `python verificar_piloto.py` para testar o recebimento e a exibição, com respostas simuladas da TotalPass.
3. Para abrir o painel, defina `PRESIQ_PANEL_PASSWORD` e `PRESIQ_WEBHOOK_SECRET` como valores diferentes, aleatórios e com pelo menos 24 caracteres. Execute `python -m flask --app server run`. Abra `http://127.0.0.1:5000/professor` com o usuário `professor` e a senha configurada.

## Cadastro e identidade visual

Abra `/configuracao` com as mesmas credenciais do painel. Preencha o nome da escola e a unidade, escolha a paleta e um símbolo, confira a prévia e salve. O painel do professor exibe as escolhas após atualizar. No celular, o formulário e os passos de integração ficam empilhados. No computador, ficam lado a lado. Esta versão piloto mantém um perfil de escola por banco, com cadastro de reservas em arquivo.

## Ativação com a unidade

1. Obtenha acesso de integrador e a chave de unidade pelo fluxo oficial da TotalPass. Use o ambiente de homologação antes da ativação real.
2. Configure a unidade e uma turma piloto em `turmas.json`. Para cada reserva, use um identificador único, a janela de chegada com fuso e o código de aluno TotalPass previamente vinculado. Confira esse campo no evento de homologação. O servidor não persiste CPF, e-mail, telefone ou o link de confirmação.
3. Hospede por HTTPS com armazenamento persistente para o SQLite (`PRESIQ_DB`) e cadastre o endereço `/integracoes/totalpass/<segredo>` no portal técnico. Redija ou desative logs que registrariam a URL secreta. Se o host autorizado de homologação for diferente do padrão, defina `TOTALPASS_HOSTS` com os domínios exatos fornecidos pelo parceiro. O painel usa uma senha compartilhada de piloto e precisa de perfis individuais antes do uso comercial.
4. Faça um check-in com um aluno de teste e uma reserva válida. Valide que o painel ficou verde e que o mesmo evento consta no histórico oficial. Repita com aluno sem vínculo e check-in expirado, que devem ficar fora da lista de liberados.

Somente a resposta HTTP 200 do parceiro libera a reserva. Uma resposta ambígua ou falha de rede vai para revisão. Se houver uma interrupção durante a confirmação, confira o histórico oficial antes de qualquer ação manual. Para produção, conecte o painel ao cadastro e à agenda persistentes da escola e implemente perfis por usuário.

### Conectar pela tela do PRESIQ

1. O responsável técnico configura no servidor `TOTALPASS_PARTNER_API_KEY` (credencial do integrador), `TOTALPASS_API_ORIGIN` (origem HTTPS da API de Check-in fornecida pela TotalPass para o ambiente), `PRESIQ_PUBLIC_URL` (origem pública HTTPS do PRESIQ), `PRESIQ_WEBHOOK_SECRET` e `PRESIQ_PANEL_PASSWORD`. O segredo do webhook deve ter pelo menos 24 caracteres, usando letras ASCII, números, hífen ou sublinhado.
2. O responsável pela escola abre **Configurar escola → Conectar TotalPass**, informa a chave da unidade do mesmo ambiente e clica em **Conectar TotalPass**. O PRESIQ autentica e solicita o cadastro do endereço que recebe os check-ins. A chave da unidade e o token não são gravados pelo formulário. Se um webhook já tiver sido cadastrado manualmente, confira a configuração existente antes de usar este botão.
3. A mensagem **Recebimento cadastrado** indica que o cadastro foi aceito. Faça um check-in de homologação e confira o resultado no painel e no histórico oficial. A implementação foi testada com respostas simuladas, incluindo o formato de token utilizado no teste. Falta verificar esse formato e o recebimento com credenciais de homologação reais.
4. Este piloto comporta uma unidade por instalação. Para trocar de unidade, configure outra instalação e coordene com a TotalPass a alteração do webhook anterior, quando aplicável.
