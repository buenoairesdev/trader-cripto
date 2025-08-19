import pandas as pd
import numpy as np

# --------------------------------------------------------------------------
# Funções Auxiliares para Médias Móveis (Replicando a função 'ma' do Pine)
# --------------------------------------------------------------------------

def sma(source: pd.Series, length: int) -> pd.Series:
    """Calcula a Média Móvel Simples (SMA)."""
    return source.rolling(window=length).mean()

def ema(source: pd.Series, length: int) -> pd.Series:
    """Calcula a Média Móvel Exponencial (EMA)."""
    return source.ewm(span=length, adjust=False).mean()

def wma(source: pd.Series, length: int) -> pd.Series:
    """Calcula a Média Móvel Ponderada (WMA)."""
    weights = np.arange(1, length + 1)
    return source.rolling(window=length).apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)

def hma(source: pd.Series, length: int) -> pd.Series:
    """Calcula a Média Móvel de Hull (HMA)."""
    half_length = int(length / 2)
    sqrt_length = int(np.sqrt(length))
    wma_half = wma(source, half_length)
    wma_full = wma(source, length)
    hma_raw = 2 * wma_half - wma_full
    return wma(hma_raw, sqrt_length)

# --- NOVA Função Auxiliar: Stochastic ---
def stochastic(source: pd.Series, high: pd.Series, low: pd.Series, length: int) -> pd.Series:
    """Calcula o %K do Estocástico."""
    lowest_low = low.rolling(window=length, min_periods=1).min()
    highest_high = high.rolling(window=length, min_periods=1).max()
    stoch_k = 100 * (source - lowest_low) / (highest_high - lowest_low)
    return stoch_k.fillna(50) # Preenche NaNs iniciais com 50 (meio do range)

# --- NOVA Função Auxiliar: f_RelVol (Volume Relativo) ---
def f_RelVol(volume_series: pd.Series, length: int) -> pd.Series:
    """Calcula o volume relativo usando Estocástico."""
    # Precisa garantir que temos high/low fictícios para o estocástico do volume
    # ou simplesmente aplicar o estocástico diretamente no volume.
    # O PineScript faz ta.stoch(_value, max_value, min_value, _length)
    # Vamos aplicar diretamente no volume:
    min_vol = volume_series.rolling(window=length, min_periods=1).min()
    max_vol = volume_series.rolling(window=length, min_periods=1).max()
    rel_vol = 100 * (volume_series - min_vol) / (max_vol - min_vol)
    # O Pine divide por 100, então:
    return (rel_vol / 100).fillna(0.5) # Preenche NaNs e normaliza entre 0 e 1


# --- Adicionar outras funções de MA conforme necessário (TEMA, DEMA, LRC, etc.) ---
# Exemplo:
# def tema(source: pd.Series, length: int) -> pd.Series:
#     ema1 = ema(source, length)
#     ema2 = ema(ema1, length)
#     ema3 = ema(ema2, length)
#     return (3 * ema1) - (3 * ema2) + ema3


# --------------------------------------------------------------------------
# Função Principal do Indicador "Ondas de Altas e Baixas"
# --------------------------------------------------------------------------

def calcular_ondas_alta_baixa(
    data: pd.DataFrame,
    coluna_preco: str = 'close', # Coluna do DataFrame com os preços de fechamento
    fast_ma_type: str = 'EMA',   # Tipo da média móvel rápida ('SMA', 'EMA', 'WMA', 'HMA', etc.) [cite: 35]
    fast_ma_length: int = 30,    # Período da média móvel rápida [cite: 36]
    slow_ma_type: str = 'SMA',   # Tipo da média móvel lenta [cite: 35]
    slow_ma_length: int = 50,    # Período da média móvel lenta [cite: 36]
    # --- Parâmetros para Heikin Ashi podem ser adicionados aqui se necessário ---
    # use_heikin_ashi: bool = True [cite: 30]
    # --- Parâmetros para MA condicional (upMA) podem ser adicionados aqui ---
    # up_ma_cond: bool = False [cite: 35]
    # up_ma_type: str = 'HMA' [cite: 35]
    # up_ma_length: int = 200 [cite: 36]
) -> pd.DataFrame:
    """
    Calcula as Médias Móveis Rápida e Lenta e identifica cruzamentos.

    Args:
        data (pd.DataFrame): DataFrame contendo os dados de mercado (OHLC).
                               Deve ter pelo menos a coluna especificada em 'coluna_preco'.
        coluna_preco (str): Nome da coluna a ser usada para os cálculos (ex: 'close', 'open').
        fast_ma_type (str): Tipo da média rápida ('SMA', 'EMA', etc.).
        fast_ma_length (int): Período da média rápida.
        slow_ma_type (str): Tipo da média lenta ('SMA', 'EMA', etc.).
        slow_ma_length (int): Período da média lenta.

    Returns:
        pd.DataFrame: DataFrame original com colunas adicionais para as médias
                      móveis e os sinais de cruzamento.
    """
    if coluna_preco not in data.columns:
        raise ValueError(f"Coluna '{coluna_preco}' não encontrada no DataFrame.")

    source = data[coluna_preco]

    # Mapeamento de tipos de MA para funções
    ma_functions = {
        'SMA': sma,
        'EMA': ema,
        'WMA': wma,
        'HMA': hma,
        # Adicionar outras MAs aqui
    }

    # Calcular Média Móvel Lenta
    if slow_ma_type in ma_functions:
        data['slow_ma'] = ma_functions[slow_ma_type](source, slow_ma_length)
    else:
        raise ValueError(f"Tipo de MA Lenta '{slow_ma_type}' não suportado.")

    # Calcular Média Móvel Rápida
    if fast_ma_type in ma_functions:
        data['fast_ma'] = ma_functions[fast_ma_type](source, fast_ma_length)
    else:
        raise ValueError(f"Tipo de MA Rápida '{fast_ma_type}' não suportado.")

    # --- Opcional: Calcular upMA condicional ---
    # if up_ma_cond and up_ma_type in ma_functions:
    #     data['up_ma'] = ma_functions[up_ma_type](source, up_ma_length)
    #     # Lógica para a 'nuvem' pode ser adicionada aqui [cite: 57]

    # Identificar Cruzamentos (Sinais)
    # Crossover (Cruzamento para Cima - Sinal de Compra Potencial) [cite: 56]
    data['crossover'] = ((data['fast_ma'] > data['slow_ma']) &
                         (data['fast_ma'].shift(1) <= data['slow_ma'].shift(1)))

    # Crossunder (Cruzamento para Baixo - Sinal de Venda Potencial) [cite: 56]
    data['crossunder'] = ((data['fast_ma'] < data['slow_ma']) &
                          (data['fast_ma'].shift(1) >= data['slow_ma'].shift(1)))

    # --- Lógica condicional baseada em upMA (se up_ma_cond=True) ---
    # if up_ma_cond and 'up_ma' in data.columns:
    #     long_condition = data['crossover'] & (data[coluna_preco] > data['up_ma']) [cite: 56, 57]
    #     short_condition = data['crossunder'] # Pine script tem 'S1 or S2'[cite: 56, 57], adaptar se necessário
    #     data['sinal_compra'] = long_condition
    #     data['sinal_venda'] = short_condition
    # else:
    data['sinal_compra'] = data['crossover']
    data['sinal_venda'] = data['crossunder']


    return data


def calcular_zonas_compra_venda(
    data: pd.DataFrame,
    periodo: int = 1500,
    high_col: str = 'high', # <-- NOVO PARÂMETRO (com valor padrão 'high')
    low_col: str = 'low'    # <-- NOVO PARÂMETRO (com valor padrão 'low')
) -> pd.DataFrame:
    """
    Calcula as Zonas de Compra e Venda baseadas nas máximas e mínimas
    de um período e níveis de Fibonacci.
    Permite especificar os nomes das colunas high/low.
    """
    # Usar os nomes das colunas passados como parâmetro
    if high_col not in data.columns or low_col not in data.columns:
        raise ValueError(f"DataFrame precisa conter colunas '{high_col}' e '{low_col}'.")

    # Calcula a máxima e mínima do período usando rolling
    highest_high = data[high_col].rolling(window=periodo, min_periods=1).max() # Usa high_col
    lowest_low = data[low_col].rolling(window=periodo, min_periods=1).min()   # Usa low_col

    # Calcula a diferença (range)
    price_range = highest_high - lowest_low

    # Calcula os níveis de Fibonacci
    data['zcv_0']   = lowest_low
    data['zcv_236'] = lowest_low + (price_range * 0.236)
    data['zcv_1000'] = lowest_low + (price_range * 0.382) #renomeei para zcv_1000 para evitar confusão com zcv_100
    data['zcv_500'] = lowest_low + (price_range * 0.500)
    data['zcv_618'] = lowest_low + (price_range * 0.618)
    data['zcv_786'] = lowest_low + (price_range * 0.786)
    data['zcv_100']  = highest_high #renomeei para zcv_100 para evitar confusão com zcv_100


    # Determinar a Zona Atual com base no preço de fechamento
    # (A lógica aqui não precisa mudar, assume que 'close' existe ou usamos 'Close'?)
    # Vamos assumir que a coluna 'Close' (maiúscula) já existe após o rename no backtester
    close_col = 'Close' if 'Close' in data.columns else 'close' # Verifica qual usar

    conditions = [
        (data[close_col] < data['zcv_236']),
        (data[close_col] >= data['zcv_236']) & (data[close_col] < data['zcv_1000']), #renomeei para zcv_1000 para evitar confusão com zcv_100
        (data[close_col] >= data['zcv_1000']) & (data[close_col] < data['zcv_618']), #renomeei para zcv_1000 para evitar confusão com zcv_100
        (data[close_col] >= data['zcv_618']) & (data[close_col] < data['zcv_786']),
        (data[close_col] >= data['zcv_786'])
    ]
    zone_names = ['Strong Buy', 'Buy', 'Neutral', 'Sell', 'Strong Sell']
    data['zcv_zona'] = np.select(conditions, zone_names, default='Neutral')

    print("Indicador Zonas de Compra/Venda calculado.")
    return data

# --------------------------------------------------------------------------
# NOVA FUNÇÃO: Indicador Sentimento VADER
# --------------------------------------------------------------------------
def calcular_sentimento_vader(
    data: pd.DataFrame,
    price_col: str = 'close',
    vol_col: str = 'volume',
    high_col: str = 'high',
    low_col: str = 'low',
    length: int = 10,
    der_avg: int = 5,
    ma_type: str = 'WMA', # WMA, EMA, SMA
    smooth: int = 3,
    show_senti: bool = False, # Se True, calcula a linha de sentimento
    senti_len: int = 20,
    v_calc: str = 'Relative', # Relative, Full, None
    vlookbk: int = 20
) -> pd.DataFrame:
    """
    Calcula o indicador de Sentimento de Mercado VADER v3.0.

    Args:
        data (pd.DataFrame): DataFrame com colunas de preço, volume, high, low.
        price_col (str): Coluna do preço (padrão 'close').
        vol_col (str): Coluna do volume (padrão 'volume').
        high_col (str): Coluna da máxima (padrão 'high').
        low_col (str): Coluna da mínima (padrão 'low').
        length (int): Período para cálculo base DER.
        der_avg (int): Período para média WMA do DER (adp, asp).
        ma_type (str): Tipo de MA para cálculo base ('WMA', 'EMA', 'SMA').
        smooth (int): Período para suavização WMA final (anp_s, V_senti).
        show_senti (bool): Calcular a linha de sentimento de longo prazo?
        senti_len (int): Período para cálculo do sentimento.
        v_calc (str): Método de cálculo do volume ('Relative', 'Full', 'None').
        vlookbk (int): Lookback para cálculo do volume relativo.

    Returns:
        pd.DataFrame: DataFrame original com colunas do VADER adicionadas:
                      'vader_adp', 'vader_asp', 'vader_anp', 'vader_signal',
                      e opcionalmente 'vader_sentiment'.
    """
    # Verificar colunas
    required = [price_col, vol_col, high_col, low_col]
    if not all(col in data.columns for col in required):
        raise ValueError(f"DataFrame precisa das colunas: {required}")

    price = data[price_col]
    volume = data[vol_col]
    high = data[high_col]
    low = data[low_col]

    # --- Seleção da função de MA ---
    ma_functions = {'SMA': sma, 'EMA': ema, 'WMA': wma}
    if ma_type not in ma_functions:
        raise ValueError(f"Tipo de MA '{ma_type}' inválido para VADER.")
    f_derma = ma_functions[ma_type]

    # --- Cálculo de Volume ('vola') ---
    if v_calc == 'None' or volume.isnull().all():
        vola = pd.Series(1.0, index=data.index) # Série de 1s
        print("VADER: Usando vola=1 (sem aceleração por volume).")
    elif v_calc == 'Relative':
        vola = f_RelVol(volume, vlookbk)
        print(f"VADER: Usando volume relativo (lookback {vlookbk}).")
    elif v_calc == 'Full':
        vola = volume
        print("VADER: Usando volume absoluto.")
    else:
        raise ValueError(f"Valor inválido para v_calc: {v_calc}")
    # Preencher NaNs iniciais em vola (importante para divisões depois)
    vola = vola.bfill().fillna(0) # Backfill e depois 0 se ainda houver NaN no início

    # --- Cálculos Core DER ---
    R = (high.rolling(window=2).max() - low.rolling(window=2).min()) / 2
    R = R.bfill().replace(0, 1e-9) # Evitar divisão por zero
    sr = price.diff() / R
    rsr = sr.clip(lower=-1, upper=1)
    c = (rsr * vola).fillna(0) # Preenche NaNs que podem surgir de rsr ou vola
    c_plus = c.clip(lower=0)
    c_minus = -c.clip(upper=0)

    # --- Cálculo DER ---
    avg_vola = f_derma(vola, length).replace(0, 1e-9) # Evitar divisão por zero
    dem = f_derma(c_plus, length) / avg_vola
    sup = f_derma(c_minus, length) / avg_vola

    # --- Médias ADP/ASP ---
    data['vader_adp'] = 100 * wma(dem, der_avg)
    data['vader_asp'] = 100 * wma(sup, der_avg)

    # --- Sinal VADER ---
    data['vader_anp'] = data['vader_adp'] - data['vader_asp']
    data['vader_signal'] = wma(data['vader_anp'], smooth)

    # --- Sentimento (Opcional) ---
    if show_senti:
        s_adp = 100 * wma(dem, senti_len)
        s_asp = 100 * wma(sup, senti_len)
        data['vader_sentiment'] = wma(s_adp - s_asp, smooth)
    else:
        data['vader_sentiment'] = np.nan # Coluna com NaN se não calculado

    print("Indicador Sentimento VADER calculado.")
    return data

# --------------------------------------------------------------------------
# Exemplo de Uso (requer dados em um DataFrame pandas)
# --------------------------------------------------------------------------

# Suponha que 'meus_dados_ohlc' é um DataFrame pandas com colunas 'open', 'high', 'low', 'close', 'volume'
# meus_dados_ohlc = pd.read_csv('seu_arquivo_de_dados.csv', index_col='timestamp', parse_dates=True) # Exemplo

# Calcular o indicador
# df_com_indicador = calcular_ondas_alta_baixa(
#     meus_dados_ohlc,
#     coluna_preco='close',
#     fast_ma_type='EMA',
#     fast_ma_length=20, # Exemplo de valores
#     slow_ma_type='SMA',
#     slow_ma_length=50  # Exemplo de valores
# )

# Visualizar os resultados
# print(df_com_indicador[['close', 'fast_ma', 'slow_ma', 'sinal_compra', 'sinal_venda']].tail())

# Plotar (requer matplotlib)
# import matplotlib.pyplot as plt
# plt.figure(figsize=(12, 6))
# plt.plot(df_com_indicador.index, df_com_indicador['close'], label='Preço Fechamento', alpha=0.5)
# plt.plot(df_com_indicador.index, df_com_indicador['fast_ma'], label='MA Rápida (EMA 20)', color='teal')
# plt.plot(df_com_indicador.index, df_com_indicador['slow_ma'], label='MA Lenta (SMA 50)', color='olive')
# # Marcar sinais
# plt.plot(df_com_indicador[df_com_indicador['sinal_compra']].index,
#          df_com_indicador['slow_ma'][df_com_indicador['sinal_compra']],
#          '^', markersize=10, color='g', lw=0, label='Sinal Compra')
# plt.plot(df_com_indicador[df_com_indicador['sinal_venda']].index,
#          df_com_indicador['slow_ma'][df_com_indicador['sinal_venda']],
#          'v', markersize=10, color='r', lw=0, label='Sinal Venda')
# plt.title('Indicador Ondas de Alta e Baixa (Python)')
# plt.legend()
# plt.show()