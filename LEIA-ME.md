# Elite Team · Protótipo de gestão de aulas

Proposta conceitual independente para a Elite Team Futevôlei, unidade Imbuí, Salvador.

## Como abrir

Abra `index.html` em Chrome, Edge, Firefox ou Safari. Não é necessário instalar dependências nem ter servidor.

## O que pode ser testado

- Agenda, cadastro de turmas, controle de vagas e reservas.
- Cadastro de alunos e reserva pela simulação da visão do aluno.
- Registro **simulado** de solicitação de check-in e validação de presença.
- Filtros, busca, exportação CSV, lembrete copiável para WhatsApp e relatório simples.
- Layout responsivo para computador e celular.
- Dados de demonstração são fictícios e ficam salvos apenas no `localStorage` do navegador.

## O que NÃO está conectado

- Nenhum sistema Wellhub, TotalPass, software de gestão atual ou banco de dados real está conectado.
- A opção de check-in mostra o fluxo de teste, **não registra presença no Wellhub**, não gera pagamento ou acesso, nem autentica a conta de alguém.
- Os números do painel são ilustrativos e não refletem a operação real da escola.
- A identidade visual é uma interpretação de conceito esportivo. A paleta exata e o logotipo oficial da Elite Team do Imbuí devem ser confirmados antes da publicação comercial.

## Caminho da integração Wellhub

1. Identificar qual CMS já é usado pela escola e confirmar a unidade parceira.
2. O responsável da escola deve abrir o Partner Portal e solicitar a avaliação em `Integrations`.
3. Com a aprovação e os detalhes técnicos obtidos, implementar uma aplicação com backend seguro e banco de dados, identidade de aluno, registro de consentimento, permissões e auditoria.
4. Implementar o conector de reservas e check-ins conforme escopos e especificações liberados pelo Wellhub, com proteção contra duplicidade, reprocessamento e tratamento de indisponibilidade.
5. Homologar com dados de teste disponibilizados pelo programa e somente depois ativar com alunos reais.

No Wellhub o aluno deve iniciar o check-in pelo aplicativo próprio e o parceiro valida a presença. Para aulas agendadas, a ação aparece de 30 minutos antes até 30 minutos depois do término; check-ins solicitados exigem validação rápida conforme a regra vigente. Uma simples reserva **não** representa uma presença validada.

Fontes oficiais:
- https://wellhub.com/en-us/partner-academy/how-check-ins-work/
- https://wellhub.com/en-us/partner-academy/cms-integration/
- https://developers.wellhub.com/
- https://wellhub.com/pt-br/search/partners/5SVou0FDhhHd7SCLEGqJcFZjalSyEwSIzQbEhaXVBUmvTYTEgtHngf19s2WP6MaP/

## Publicação no Render

Se desejar publicar esta demonstração, coloque `index.html` na raiz de um repositório GitHub e crie um `Static Site` no Render: `Branch: main`, `Build command: echo pronto`, `Publish directory: .`. A publicação estática não transforma o protótipo em sistema multiusuário e não liga o Wellhub.
