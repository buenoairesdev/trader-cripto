# 🤖 trader-cripto
*Um conjunto de ferramentas de análise técnica e trading para criptomoedas na exchange Bybit.*

## 📖 Sobre o Projeto
`trader-cripto` é um projeto em Python desenvolvido para análise de estratégias de trading e execução de operações no mercado de futuros de criptomoedas. O núcleo do projeto combina múltiplos indicadores técnicos para gerar sinais de compra e venda, permitindo a análise visual e o backtesting de estratégias, além da execução de ordens reais ou em ambiente de teste (testnet) através da API da Bybit.

A principal estratégia analisada combina três indicadores distintos:
1.  **Ondas de Alta e Baixa:** Baseado no cruzamento de duas médias móveis (configuráveis) para identificar a tendência de curto e médio prazo.
2.  **Zonas de Compra e Venda:** Um indicador baseado em níveis de Fibonacci calculados a partir das máximas e mínimas de um longo período, demarcando zonas de sobrecompra e sobrevenda.
3.  **Sentimento VADER:** Um oscilador de sentimento de mercado que utiliza o volume para medir a pressão compradora (demanda) e vendedora (oferta).

O projeto permite ao usuário visualizar graficamente como esses indicadores interagem com o preço e como os sinais de trading são gerados a partir da confluência de seus sinais.

## ✨ Principais Funcionalidades
- **Conexão com a API da Bybit:** Interage com a API v5 da Bybit para dados de mercado e execução de ordens.
- **Cálculo de Indicadores Técnicos:**
    - Médias Móveis (SMA, EMA, WMA, HMA).
    - Indicador "Ondas de Alta e Baixa" por cruzamento de MAs.
    - Indicador "Zonas de Compra e Venda" com níveis de Fibonacci.
    - Indicador de sentimento de mercado "VADER" baseado em volume.
- **Análise de Estratégia:** Combina os indicadores para gerar sinais de compra/venda baseados em duas lógicas de confluência (Estratégia A e B).
- **Visualização de Dados:** Plota gráficos detalhados com `matplotlib`, exibindo o preço, indicadores e os sinais de trade gerados.
- **Execução de Ordens:** Módulo para colocar ordens de mercado (`Market`), definir alavancagem, e gerenciar Stop Loss e Take Profit.
- **Monitoramento de Posições:** Script para monitorar posições abertas em tempo real e salvar os dados em um arquivo `JSON` para consumo externo (ex: dashboards).
- **Backtesting:** Inclui um backtester para validar a eficácia das estratégias com dados históricos.
- **Dashboard de Resultados:** Um dashboard web (`Flask`/`Dash`) para visualizar os resultados dos backtests de forma interativa.

## 🛠️ Tecnologias Utilizadas
- **Linguagem:** Python 3
- **Análise de Dados e Numérica:**
    - Pandas
    - NumPy
- **Conexão com API:**
    - pybit
- **Visualização de Dados:**
    - Matplotlib
- **Dashboard (inferido):**
    - Flask
    - Dash / Plotly

## 🚀 Instalação e Configuração

**1. Clone o repositório:**
```bash
git clone https://github.com/buenozinresdev/trader-cripto.git
cd trader-cripto
```

**2. Crie um Ambiente Virtual e Instale as Dependências:**
É altamente recomendado usar um ambiente virtual para isolar as dependências do projeto.
```bash
# Crie o ambiente virtual
python -m venv venv

# Ative o ambiente (Windows)
.\venv\Scripts\activate

# Ative o ambiente (Linux/macOS)
source venv/bin/activate

# Instale as dependências
pip install pandas numpy matplotlib pybit
# Para o dashboard, você também pode precisar de:
# pip install dash plotly
```

**3. Configure suas Chaves de API:**
Para utilizar os scripts que interagem com a Bybit (`bybit_trade_manager.py`), você precisa de uma chave de API e um segredo.

- **Para Testnet (Ambiente de Teste):**
    1. Crie uma conta em [https://testnet.bybit.com/](https://testnet.bybit.com/).
    2. Gere suas chaves de API na plataforma.
    3. Abra o arquivo `bybit_trade_manager.py` e insira sua chave e segredo nas variáveis `bybit_api_key` e `bybit_api_secret` dentro do bloco `if __name__ == "__main__":`.

- **Para a Rede Principal (Live Trading):**
    1. **Com muito cuidado**, você pode alterar a variável `TESTNET_MODE` para `False`.
    2. Insira suas chaves de API da sua conta real da Bybit.
    **Atenção:** Operar na rede principal envolve risco financeiro real. Comece sempre pela Testnet.

## 📈 Como Usar

### Análise de Estratégia
Para analisar uma estratégia para um par de moedas específico e visualizar o gráfico:
1.  Abra o arquivo `main.py`.
2.  Ajuste os parâmetros na seção `--- Definição dos Parâmetros ---`, como `symbol_to_fetch`, `interval_to_fetch`, e as configurações dos indicadores.
3.  Execute o script:
    ```bash
    python main.py
    ```
    Isso irá buscar os dados mais recentes, calcular os indicadores e exibir um gráfico com os sinais.

### Monitoramento de Posições
Para monitorar suas posições abertas na Bybit e salvá-las em `bybit_positions.json`:
1.  Configure suas chaves de API em `bybit_trade_manager.py`.
2.  Execute o script:
    ```bash
    python bybit_trade_manager.py
    ```
    O script ficará em execução, atualizando o arquivo JSON a cada 10 segundos. Pressione `CTRL+C` para parar.

### Backtesting e Dashboard
Consulte os scripts `backtester.py` e o diretório `dashboard_backtest` para funcionalidades de teste de estratégia e visualização de resultados.

---

*Este projeto é fornecido para fins educacionais e de pesquisa. O trading de criptomoedas envolve alto risco. O autor não se responsabiliza por quaisquer perdas financeiras.*
