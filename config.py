# ==============================================================================
# ARQUIVO DE CONFIGURAÇÃO CENTRAL PARA O PROJETO TRADER-CRIPTO
# ==============================================================================
#
# Instruções:
# - Altere os parâmetros nesta seção para configurar o comportamento do backtester.
# - Não é necessário alterar o código do backtester.py para rodar com novas configs.
# ==============================================================================

# --- MODO DE EXECUÇÃO ---
# True para otimizar os parâmetros definidos em `RANGES_OTIMIZACAO`.
# False para rodar um único backtest com os parâmetros padrão definidos na estratégia.
MODO_OTIMIZACAO = True
USE_DUMMY_DATA = False # Para testes locais com dummy_data.csv

# --- PARÂMETROS GERAIS DE BACKTEST ---
# Lista de ativos para fazer o backtest. Ex: ["BTCUSDT", "ETHUSDT"]
COINS = ["HYPEUSDT", "TRUMPUSDT", "ENAUSDT", "ONDOUSDT", "1000BONKUSDT", "1000PEPEUSDT"]

# Timeframe em minutos. Ex: '1', '3', '5', '15', '60' (para 1h), 'D' (para diário)
TIMEFRAME = '5'

# Número de dias de histórico para buscar para o backtest.
DIAS_HISTORICO = 30

# --- PARÂMETROS FINANCEIROS ---
# Capital inicial para cada backtest.
INITIAL_CASH = 10000.0

# Taxa de comissão por trade (ex: 0.0006 para 0.06%).
COMMISSION_RATE = 0.0006

# Fração do equity a ser usada como margem para cada trade.
# A biblioteca backtesting.py usa isso para checagens internas.
MARGIN_PARAM = 0.0476 # Equivalente a ~21x de alavancagem (1 / 0.0476)

# Fração do equity total a ser arriscada em cada trade.
# Este é o principal controle do tamanho da posição.
EQUITY_FRACTION_PER_TRADE = 0.048

# --- PARÂMETROS DA API BYBIT ---
# Categoria de trading para a API. 'linear' para futuros USDT, 'spot' para mercado à vista.
TRADE_CATEGORY = 'linear'

# --- PARÂMETROS FIXOS DOS INDICADORES ---
# Período para o indicador de Zonas de Compra/Venda.
ZONAS_PERIODO = 1500

# Período para o cálculo do Average True Range (ATR), usado no Stop Loss dinâmico.
ATR_PERIODO = 14

# Parâmetros para o indicador VADER.
VADER_PARAMS = {
    'length': 10, 'der_avg': 5, 'ma_type': 'WMA', 'smooth': 3,
    'show_senti': False, 'senti_len': 20, 'v_calc': 'Relative', 'vlookbk': 20
}

# --- FILTROS AVANÇADOS DA ESTRATÉGIA ---
USAR_FILTRO_REGIME_MERCADO = True  # True para usar o filtro de tendência de longo prazo (ex: EMA 200 Diária)
USAR_FILTRO_STOCH_RSI = True       # True para usar o filtro de confirmação do StochRSI

# Parâmetros para o Filtro de Regime de Mercado
REGIME_FILTER_PARAMS = {
    'timeframe': 'D',      # Timeframe para calcular a MA de tendência ('D', '240', etc.)
    'ma_periodo': 200,     # Período da Média Móvel de tendência
}

# Parâmetros para o Filtro Stochastic RSI
STOCH_RSI_FILTER_PARAMS = {
    'periodo_rsi': 14,
    'periodo_stoch': 14,
    'periodo_k': 3,
    'periodo_d': 3,
    'limite_compra': 80,  # Não comprar se StochRSI > 80 (evitar sobrecompra)
    'limite_venda': 20,   # Não vender se StochRSI < 20 (evitar sobrevenda)
}

# --- PARÂMETROS DA ESTRATÉGIA (Usados no modo NÃO OTIMIZADO) ---
# Tipos de Média Móvel a serem usados na estratégia.
# Opções: 'SMA', 'EMA', 'WMA', 'HMA'
FAST_MA_TYPE = 'EMA'
SLOW_MA_TYPE = 'EMA'

# Parâmetros padrão para a estratégia quando MODO_OTIMIZACAO = False
# Estes valores serão usados diretamente no backtest.
PARAMETROS_PADRAO = {
    'fast_ma_len_otim': 12,
    'slow_ma_len_otim': 26,
    'multiplicador_sl_atr': 2.0,
    'tp_rr_otim': 2.0,
}

# --- CONFIGURAÇÕES DE OTIMIZAÇÃO (Usados quando MODO_OTIMIZACAO = True) ---
# Métrica alvo para a otimização. O backtester tentará maximizar este valor.
# Opções comuns: 'Sharpe Ratio', 'Sortino Ratio', 'Calmar Ratio', 'Return [%]', 'Win Rate [%]'
METRICA_OTIMIZACAO = 'Sortino Ratio'

# Se True, salva os resultados da execução final (com os melhores parâmetros) no banco de dados.
# Se False, apenas a otimização é rodada, mas os resultados finais não são salvos.
SALVAR_RESULTADOS_OTIMIZADOS_NO_DB = True

# Ranges de parâmetros para testar durante a otimização.
# NOTA: O número de combinações é o produto do tamanho de cada lista/range.
# Cuidado para não criar um número excessivamente grande de combinações.
RANGES_OTIMIZACAO = {
    'multiplicador_sl_atr': [1.5, 2.0, 2.5, 3.0, 3.5], # Multiplicador para o Stop Loss dinâmico (ATR)
    'tp_rr_otim': [1.0, 1.5, 2.0, 2.5], # Risco/Retorno para o Take Profit
    'fast_ma_len_otim': range(5, 38, 4), # Período da MA rápida
    'slow_ma_len_otim': range(30, 101, 10), # Período da MA lenta
}

# Número de workers para usar durante a otimização.
# `None` ou `1` para desativar paralelismo.
# `-1` para usar todos os cores de CPU disponíveis (recomendado para velocidade).
MAX_WORKERS_OTIMIZACAO = -1
