# backtester.py (Versão Final Otimizada e Refinada)

import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
from datetime import datetime, timezone, timedelta
import json
import traceback
import os  # Para os.cpu_count() (opcional, para max_workers)

# --- Importações de Módulos Locais ---
# É crucial que estes arquivos existam e estejam corretos.
try:
    from database_manager import create_tables, registrar_execucao, registrar_resultados_ativos
    # create_tables() # Garante que as tabelas existam (opcional, descomente se necessário)
    DB_MANAGER_AVAILABLE = True
except ImportError:
    DB_MANAGER_AVAILABLE = False
    print("AVISO: database_manager.py não encontrado. Os resultados não serão salvos no banco de dados.")

try:
    from bybit_data import fetch_bybit_kline
except ImportError:
    print("ERRO CRÍTICO: bybit_data.py não encontrado. Não é possível buscar dados.")
    exit()

try:
    from indicadores import (
        calcular_zonas_compra_venda,
        calcular_sentimento_vader,
        sma, ema, wma, hma
    )
except ImportError:
    print("ERRO CRÍTICO: indicadores.py não encontrado ou funções ausentes.")
    exit()

# Descomente a linha abaixo se quiser usar a visualização matplotlib no final deste script
# from visualizacao_resultados import gerar_visualizacoes

# --- Classe da Estratégia ---


class EstrategiaMultiIndicador(Strategy):
    """
    Estratégia que combina cruzamento de Médias Móveis (otimizável),
    Zonas de Compra/Venda (fixo) e VADER (fixo) para gerar sinais.
    SL e TP também são otimizáveis.
    """
    # --- Parâmetros Otimizáveis (com valores padrão que serão usados se MODO_OTIMIZACAO=False) ---
    fast_ma_len_otim = 12   # Período da MA rápida
    slow_ma_len_otim = 26   # Período da MA lenta
    sl_percent_otim = 0.02  # Stop Loss percentual
    tp_rr_otim = 2.0        # Take Profit baseado em Risco/Retorno (RR)

    # --- Parâmetros de Configuração Fixos ---
    fast_ma_type_est = 'EMA'  # Tipo de MA rápida ('SMA', 'EMA', 'WMA', 'HMA')
    slow_ma_type_est = 'EMA'  # Tipo de MA lenta
    equity_fraction_per_trade = 0.048  # Fração do equity a ser usada por trade
    asset_name_param = "N/A_Asset"  # Nome do ativo (passado como parâmetro)

    max_workers = None  # Atributo dummy, não usado diretamente

    def init(self):
        """
        Inicializa a estratégia: calcula MAs (com params otimizáveis) e prepara séries de sinais.
        Indicadores Zonas e Vader são pré-calculados e acessados via self.data.
        """
        current_index = pd.to_datetime(self.data.index)
        close_series = pd.Series(self.data.Close, index=current_index)

        ma_functions = {'SMA': sma, 'EMA': ema, 'WMA': wma, 'HMA': hma}
        try:
            func_ma_rapida = ma_functions[self.fast_ma_type_est]
            func_ma_lenta = ma_functions[self.slow_ma_type_est]
        except KeyError:
            raise ValueError(
                f"Tipo de MA inválido: Rápida ('{self.fast_ma_type_est}'), Lenta ('{self.slow_ma_type_est}')")

        # Garante que os períodos sejam inteiros
        fast_len = int(self.fast_ma_len_otim)
        slow_len = int(self.slow_ma_len_otim)

        # Calcula as Médias Móveis
        ma_rapida_series = func_ma_rapida(close_series, fast_len)
        ma_lenta_series = func_ma_lenta(close_series, slow_len)

        # Calcula sinais de cruzamento de MMs
        self.sinal_compra_mm_series = ((ma_rapida_series > ma_lenta_series) & (
            ma_rapida_series.shift(1) <= ma_lenta_series.shift(1)))
        self.sinal_venda_mm_series = ((ma_rapida_series < ma_lenta_series) & (
            ma_rapida_series.shift(1) >= ma_lenta_series.shift(1)))

        # Acessa indicadores pré-calculados (Zonas e Vader) como pd.Series
        self.zcv_zona_num_series_pd = pd.Series(
            self.data.ZCV_Zona_Num_I, index=current_index)
        self.vader_signal_series_pd = pd.Series(
            self.data.VADER_Signal_I, index=current_index)

        # Combina os sinais para gerar as condições finais de entrada
        cond_ondas_compra = self.sinal_compra_mm_series == True
        cond_zonas_compra = self.zcv_zona_num_series_pd.isin(
            [1, 2])  # Zona Buy ou Strong Buy
        cond_vader_positivo = self.vader_signal_series_pd > 0
        cond_vader_cruzou_zero_up = (self.vader_signal_series_pd > 0) & (
            self.vader_signal_series_pd.shift(1) <= 0)

        cond_ondas_venda = self.sinal_venda_mm_series == True
        cond_zonas_venda = self.zcv_zona_num_series_pd.isin(
            [-1, -2])  # Zona Sell ou Strong Sell
        cond_vader_negativo = self.vader_signal_series_pd < 0
        cond_vader_cruzou_zero_down = (self.vader_signal_series_pd < 0) & (
            self.vader_signal_series_pd.shift(1) >= 0)

        # Estratégia A: Ondas + Zonas + Direção Vader
        self.compra_a_series = (
            cond_ondas_compra & cond_zonas_compra & cond_vader_positivo).fillna(False)
        self.venda_a_series = (
            cond_ondas_venda & cond_zonas_venda & cond_vader_negativo).fillna(False)
        # Estratégia B: Ondas + Zonas + Cruzamento Vader
        self.compra_b_series = (
            cond_ondas_compra & cond_zonas_compra & cond_vader_cruzou_zero_up).fillna(False)
        self.venda_b_series = (
            cond_ondas_venda & cond_zonas_venda & cond_vader_cruzou_zero_down).fillna(False)

        # Define SL e TP finais (convertidos para float para segurança)
        self.sl_percent_final = float(self.sl_percent_otim)
        self.tp_rr_final = float(self.tp_rr_otim)

        # --- LOG DE RESUMO INIT (Pode ser comentado se não for necessário) ---
        # print(f"--- Resumo INIT Estratégia para: {self.asset_name_param} ---")
        # print(f"Params: MA({fast_len}/{slow_len}), SL%({self.sl_percent_final:.2f}), TP_RR({self.tp_rr_final:.1f})")
        # print(f"Sinais Finais Gerados: CA:{self.compra_a_series.sum()}, CB:{self.compra_b_series.sum()} | VA:{self.venda_a_series.sum()}, VB:{self.venda_b_series.sum()}")
        # --- FIM LOG INIT ---

    def next(self):
        """
        Método chamado para cada vela de dados. Verifica os sinais e executa ordens.
        """
        current_time_idx = self.data.index[-1]  # Índice (Timestamp) da vela atual

        # Verifica se as séries de sinais existem (devem ter sido criadas no init)
        if not hasattr(self, 'compra_a_series'):
            return  # Sai se as séries não estiverem prontas

        # Busca o valor do sinal correspondente ao índice da vela atual
        try:
            sinal_compra_a_atual = self.compra_a_series[current_time_idx]
            sinal_venda_a_atual = self.venda_a_series[current_time_idx]
            sinal_compra_b_atual = self.compra_b_series[current_time_idx]
            sinal_venda_b_atual = self.venda_b_series[current_time_idx]
        except KeyError:
            # print(f"AVISO KEYERROR [{self.asset_name_param}] em {current_time_idx}: Índice não encontrado nas séries de sinais.")
            return  # Pula esta vela se não encontrar o índice

        preco_atual = self.data.Close[-1]  # Preço de fechamento da vela atual

        # Lógica de entrada: Apenas entra se não houver posição aberta
        if not self.position:
            entrada_compra = False
            entrada_venda = False

            # Verifica se alguma condição de compra (A ou B) é verdadeira
            if sinal_compra_a_atual or sinal_compra_b_atual:
                entrada_compra = True
            # Senão, verifica se alguma condição de venda (A ou B) é verdadeira
            elif sinal_venda_a_atual or sinal_venda_b_atual:
                entrada_venda = True

            # Se uma condição de entrada foi atendida
            if entrada_compra or entrada_venda:
                # print(f"ORDEM [{self.asset_name_param}] em {current_time_idx}: Tentando {'COMPRA' if entrada_compra else 'VENDA'} @{preco_atual:.4f}")
                preco_entrada = preco_atual
                # Calcula o tamanho da posição com base na fração do equity
                size_to_use = self.equity_fraction_per_trade

                # Executa a ordem de Compra
                if entrada_compra:
                    sl_price = preco_entrada * (1 - self.sl_percent_final)
                    tp_price = preco_entrada + \
                        (preco_entrada - sl_price) * self.tp_rr_final
                    try:
                        self.buy(size=size_to_use, sl=sl_price, tp=tp_price)
                        # print(f"ORDEM [{self.asset_name_param}] em {current_time_idx}: COMPRA OK. SL:{sl_price:.4f}, TP:{tp_price:.4f}")
                    # Captura exceções potenciais (ex: margem insuficiente)
                    except Exception as e_buy:
                        print(
                            f"AVISO BUY [{self.asset_name_param}]@{current_time_idx}: Falha - {type(e_buy).__name__}: {e_buy}")
                        pass  # Ignora a ordem se falhar

                # Executa a ordem de Venda
                elif entrada_venda:
                    sl_price = preco_entrada * (1 + self.sl_percent_final)
                    tp_price = preco_entrada - \
                        (sl_price - preco_entrada) * self.tp_rr_final
                    try:
                        self.sell(size=size_to_use, sl=sl_price, tp=tp_price)
                        # print(f"ORDEM [{self.asset_name_param}] em {current_time_idx}: VENDA OK. SL:{sl_price:.4f}, TP:{tp_price:.4f}")
                    except Exception as e_sell:  # Captura exceções potenciais
                        print(
                            f"AVISO SELL [{self.asset_name_param}]@{current_time_idx}: Falha - {type(e_sell).__name__}: {e_sell}")
                        pass  # Ignora a ordem se falhar


# --------------------------------------------------
# 1. Configurações Globais do Script
# --------------------------------------------------
# > 'Sharpe Ratio' 'Sortino Ratio 'Calmar Ratio' 'Win Rate [%]' 'Max. Drawdown [%]' 'Return [%]'
# True para otimizar, False para rodar com params padrão
MODO_OTIMIZACAO = True
# Salvar os resultados do run final após otimização?
SALVAR_RESULTADOS_OTIMIZADOS_NO_DB = True
METRICA_OTIMIZACAO = 'Sortino Ratio'    # Métrica alvo para a otimização

# --- Ativos e Período ---
# Adicione mais ativos conforme necessário
coins = ["HYPEUSDT", "TRUMPUSDT", "ENAUSDT", "ONDOUSDT", "1000BONKUSDT", "1000PEPEUSDT"]
# Intervalo em minutos ('1', '3', '5', '15', '60', 'D', etc.)
timeframe = '1'
days_history = 30                         # Número de dias de histórico para buscar
end_date_dt = datetime.now(timezone.utc)  # Data final (agora)
start_date_dt = end_date_dt - timedelta(days=days_history)  # Data inicial

print(f"Iniciando script. MODO_OTIMIZACAO: {MODO_OTIMIZACAO}")
if MODO_OTIMIZACAO:
    print(f"Métrica Alvo para Otimização: {METRICA_OTIMIZACAO}")
print(f"Período: {start_date_dt.strftime('%Y-%m-%d %H:%M')} a {end_date_dt.strftime('%Y-%m-%d %H:%M')} ({days_history} dias)")
print(f"Timeframe: {timeframe} minutos")

# --- Parâmetros Fixos dos Indicadores (não otimizados aqui) ---
zonas_periodo_padrao = 1500
vader_params_padrao = {
    'length': 10, 'der_avg': 5, 'ma_type': 'WMA', 'smooth': 3,
    'show_senti': False, 'senti_len': 20, 'v_calc': 'Relative', 'vlookbk': 20
}
fast_ma_type_est_cfg = EstrategiaMultiIndicador.fast_ma_type_est  # Guardado para log/DB
slow_ma_type_est_cfg = EstrategiaMultiIndicador.slow_ma_type_est  # Guardado para log/DB

# --- Ranges para Otimização (usados apenas se MODO_OTIMIZACAO = True) ---
# Ajuste estes ranges conforme necessário para encontrar os melhores parâmetros
params_otimizacao_ranges = {
    # SL: 1% a 4% (Lista explícita)
    'sl_percent_otim': [0.0075, 0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045],
    # Risco/Retorno: 1:1 a 1:3 (Lista explícita)
    'tp_rr_otim': [0.8, 1.0, 1.25, 1.5, 2.0],
    # MA Rápida: 10, 15, 20, 25, 30 (range correto)
    'fast_ma_len_otim': range(5, 38, 4),
    # MA Lenta: 30, 40, 50, 60, 70 (range correto)
    'slow_ma_len_otim': range(30, 101, 10),
}
# Verifica o número total de combinações
num_combinacoes = 1
if MODO_OTIMIZACAO:
    for k, v in params_otimizacao_ranges.items():
        num_combinacoes *= len(v)
    print(
        f"Número total de combinações por ativo na otimização: {num_combinacoes}")

# --- Configurações do Backtest ---
initial_cash = 10000.0     # Capital inicial
commission_rate = 0.0006  # Comissão por trade (ex: 0.06%)
# Fração do equity usada como margem (1.0 = sem alavancagem no cálculo do size)
margin_param = 0.0476
# NOTA: O size ainda é 'equity_fraction_per_trade' do capital total.
# A biblioteca backtesting.py usa 'margin' para checagens internas,
# mas o controle efetivo do tamanho está em 'equity_fraction_per_trade'.

# --- Coleta de Resultados ---
# Lista para armazenar estatísticas de cada ativo
all_stats_list_para_df_final = []
id_execucao_principal_script = None    # ID da execução no banco de dados
# Dicionário para guardar parâmetros usados por ativo
active_parameters_for_run_dict = {}

# --------------------------------------------------
# 2. Loop Principal por Ativo
# --------------------------------------------------
for coin in coins:
    print(f"\n{'='*20} Processando {coin} {'='*20}")
    active_parameters_for_run_dict[coin] = {}  # Reseta para o ativo atual
    try:
        # --- A. Busca de Dados ---
        print(f"Buscando dados para {coin}...")
        df_raw = fetch_bybit_kline(symbol=coin, interval=timeframe,
                                   start_time_dt=start_date_dt, end_time_dt=end_date_dt, category='linear')

        # Calcula o mínimo de velas necessárias baseado nos períodos dos indicadores
        min_len_ma_otim = 0
        if MODO_OTIMIZACAO and params_otimizacao_ranges.get('slow_ma_len_otim'):
            min_len_ma_otim = max(
                params_otimizacao_ranges['slow_ma_len_otim'])
        min_candles_necessarias = max(zonas_periodo_padrao, vader_params_padrao.get('vlookbk', 20),
                                      min_len_ma_otim, EstrategiaMultiIndicador.slow_ma_len_otim) + 50  # Folga

        if df_raw.empty or len(df_raw) < min_candles_necessarias:
            print(
                f"AVISO: Dados insuficientes para {coin} ({len(df_raw)} velas, precisa de ~{min_candles_necessarias}). Pulando...")
            # Registra como erro para visualização final
            all_stats_list_para_df_final.append({'Asset': coin, '# Trades': -1, 'Otimizado': MODO_OTIMIZACAO,
                                                'Descricao_Estrategia': f'Dados Insuficientes ({len(df_raw)}/{min_candles_necessarias})'})
            continue

        # Prepara o DataFrame: renomeia colunas, define índice
        df_bt = df_raw.rename(columns={
                              'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        df_bt.index = pd.to_datetime(df_bt.index)

        # --- B. Cálculo de Indicadores Fixos (Zonas, Vader) ---
        print(f"Calculando indicadores fixos para {coin} (Zonas, Vader)...")
        df_bt = calcular_zonas_compra_venda(
            df_bt, high_col='High', low_col='Low', periodo=zonas_periodo_padrao)
        df_bt = calcular_sentimento_vader(
            df_bt, price_col='Close', vol_col='Volume', high_col='High', low_col='Low', **vader_params_padrao)

        # Mapeia Zonas string para números e renomeia para o backtest
        zonas_map = {'Strong Buy': 2, 'Buy': 1,
                     'Neutral': 0, 'Sell': -1, 'Strong Sell': -2}
        df_bt['ZCV_Zona_Num_Map'] = df_bt['zcv_zona'].map(zonas_map).fillna(0)
        df_bt.rename(columns={'ZCV_Zona_Num_Map': 'ZCV_Zona_Num_I',
                     'vader_signal': 'VADER_Signal_I'}, inplace=True)

        # Remove linhas com NaN nas colunas essenciais para o backtest
        colunas_essenciais_para_bt = [
            'Open', 'High', 'Low', 'Close', 'Volume', 'ZCV_Zona_Num_I', 'VADER_Signal_I']
        df_bt.dropna(subset=colunas_essenciais_para_bt, inplace=True)

        if df_bt.empty:
            print(
                f"AVISO: DataFrame para {coin} ficou VAZIO após dropna das colunas essenciais. Pulando...")
            all_stats_list_para_df_final.append(
                {'Asset': coin, '# Trades': -1, 'Otimizado': MODO_OTIMIZACAO, 'Descricao_Estrategia': 'DataFrame Vazio Pós-Dropna'})
            continue

        print(
            f"Dados preparados para Backtest (após dropna): {len(df_bt)} velas.")
        df_para_bt_final = df_bt[colunas_essenciais_para_bt].copy()

        # --- C. Instanciar Backtest ---
        bt = Backtest(df_para_bt_final, EstrategiaMultiIndicador,
                      cash=initial_cash, commission=commission_rate,
                      margin=margin_param, trade_on_close=True, exclusive_orders=True)

        # Parâmetros fixos a serem passados para run/optimize (ex: nome do ativo)
        params_para_rodada = {'asset_name_param': coin}

        # --- D. Executar Otimização ou Backtest Normal ---
        if MODO_OTIMIZACAO:
            print(
                f"Rodando OTIMIZAÇÃO para {coin} | Alvo: {METRICA_OTIMIZACAO}...")
            print(f"Ranges de otimização: {params_otimizacao_ranges}")
            # Filtra ranges para garantir que correspondem a atributos otimizáveis na estratégia
            valid_otim_params_ranges = {k: v for k, v in params_otimizacao_ranges.items(
            ) if hasattr(EstrategiaMultiIndicador, k)}

            # Mantenha 1 para estabilidade inicial. Aumente se necessário e monitorar.
            workers_otim = 14
            print(f"Otimização será executada com max_workers={workers_otim}")

            # Executa a otimização
            stats_otimizacao, heatmap = bt.optimize(
                maximize=METRICA_OTIMIZACAO,
                return_heatmap=True,
                # Garante que MA rápida seja menor que MA lenta
                constraint=lambda p: p.fast_ma_len_otim < p.slow_ma_len_otim if hasattr(
                    p, 'fast_ma_len_otim') and hasattr(p, 'slow_ma_len_otim') else True,
                max_workers=workers_otim,
                **valid_otim_params_ranges,  # Ranges dos parâmetros a otimizar
                **params_para_rodada        # Parâmetros fixos como asset_name_param
            )

            print(f"\n--- Resultados da Otimização para {coin} ---")
            metric_value = stats_otimizacao.get(METRICA_OTIMIZACAO)
            print(f"Valor da Métrica Otimizada ({METRICA_OTIMIZACAO}): {metric_value:.4f}" if pd.notna(
                metric_value) else f"Valor da Métrica Otimizada ({METRICA_OTIMIZACAO}): N/A")

            # Verifica se a otimização encontrou uma estratégia válida
            if hasattr(stats_otimizacao, '_strategy') and stats_otimizacao._strategy:
                melhores_params_obj = stats_otimizacao._strategy
                # Guarda os melhores parâmetros encontrados
                active_parameters_for_run_dict[coin] = {k: getattr(
                    melhores_params_obj, k, None) for k in valid_otim_params_ranges.keys()}
                print("Melhores Parâmetros Encontrados:")
                for p_nome, p_valor in active_parameters_for_run_dict[coin].items():
                    print(f"  {p_nome}: {p_valor:.4f}" if isinstance(
                        p_valor, float) else f"  {p_nome}: {p_valor}")

                # Prepara parâmetros para o run final (melhores + fixos)
                run_final_params = {
                    **active_parameters_for_run_dict[coin], **params_para_rodada}
                desc_parts = [f"{k.replace('_otim','').upper()} {v:.0f}" if isinstance(
                    v, int) else f"{k.replace('_otim','').upper()} {v:.2f}" for k, v in active_parameters_for_run_dict[coin].items()]
                descricao_final_para_db = f"Otim ({METRICA_OTIMIZACAO[:4]}): {', '.join(desc_parts)} | TF{timeframe}m, {days_history}d"

                # Executa o backtest final com os melhores parâmetros
                print(
                    f"\nRodando backtest final para {coin} com parâmetros otimizados...")
                stats_run_final_otimizado = bt.run(**run_final_params)
                current_run_stats_dict = stats_run_final_otimizado.to_dict()
                print(
                    f"Estatísticas do run final otimizado para {coin} coletadas (# Trades: {current_run_stats_dict.get('# Trades', 'N/A')}).")

                # --- INÍCIO DA MODIFICAÇÃO: Coletar Equity Curve e Trades ---
                if hasattr(stats_run_final_otimizado, '_equity_curve') and stats_run_final_otimizado._equity_curve is not None:
                    # _equity_curve é um DataFrame. Salvar como JSON (orient='split' é bom para recriar o DF)
                    try:
                        current_run_stats_dict['EquityCurve_JSON'] = stats_run_final_otimizado._equity_curve.to_json(
                            orient='split', date_format='iso')
                    except Exception as e_json_eq:
                        print(
                            f"AVISO: Falha ao converter _equity_curve para JSON para {coin}: {e_json_eq}")
                        current_run_stats_dict['EquityCurve_JSON'] = None
                else:
                    current_run_stats_dict['EquityCurve_JSON'] = None

                if hasattr(stats_run_final_otimizado, '_trades') and stats_run_final_otimizado._trades is not None and not stats_run_final_otimizado._trades.empty:
                    # _trades é um DataFrame. Salvar como JSON.
                    try:
                        current_run_stats_dict['Trades_JSON'] = stats_run_final_otimizado._trades.to_json(
                            orient='split', date_format='iso')
                    except Exception as e_json_tr:
                        print(
                            f"AVISO: Falha ao converter _trades para JSON para {coin}: {e_json_tr}")
                        current_run_stats_dict['Trades_JSON'] = None
                else:
                    current_run_stats_dict['Trades_JSON'] = None
                # --- FIM DA MODIFICAÇÃO ---

                # Adiciona informações extras ao dicionário de estatísticas
                current_run_stats_dict['Asset'] = coin
                current_run_stats_dict['Otimizado'] = True
                # Limita tamanho
                current_run_stats_dict['Descricao_Estrategia'] = descricao_final_para_db[:250]
                all_stats_list_para_df_final.append(current_run_stats_dict)
            else:  # Caso a otimização não retorne uma _strategy válida
                print(
                    f"AVISO: Objeto _strategy não encontrado nos resultados da otimização para {coin}.")
                # Pega as stats gerais da otimização
                stats_dict_coleta = stats_otimizacao.to_dict()
                active_parameters_for_run_dict[coin] = {  # Usa o primeiro valor dos ranges como fallback
                    k: v[0] if isinstance(v, (list, range)) else v
                    for k, v in valid_otim_params_ranges.items()
                }
                stats_dict_coleta['Asset'] = coin
                stats_dict_coleta['Otimizado'] = True
                stats_dict_coleta['Descricao_Estrategia'] = f"Otim ({METRICA_OTIMIZACAO[:4]}) - Falha Params"
                all_stats_list_para_df_final.append(stats_dict_coleta)

        else:  # MODO_OTIMIZACAO == False
            print(f"Rodando backtest PADRÃO para {coin}...")
            # Usa os parâmetros padrão definidos na classe da Estratégia
            active_parameters_for_run_dict[coin] = {
                'fast_ma_len_otim': EstrategiaMultiIndicador.fast_ma_len_otim,
                'slow_ma_len_otim': EstrategiaMultiIndicador.slow_ma_len_otim,
                'sl_percent_otim': EstrategiaMultiIndicador.sl_percent_otim,
                'tp_rr_otim': EstrategiaMultiIndicador.tp_rr_otim,
            }
            # Combina parâmetros padrão com fixos (como asset_name_param)
            run_params = {
                **active_parameters_for_run_dict[coin], **params_para_rodada}
            stats_run_normal = bt.run(**run_params)
            print(
                f"Estatísticas do run normal para {coin} coletadas (# Trades: {stats_run_normal.get('# Trades', 'N/A')}).")

            # --- INÍCIO DA MODIFICAÇÃO: Coletar Equity Curve e Trades para run normal ---
            if hasattr(stats_run_normal, '_equity_curve') and stats_run_normal._equity_curve is not None:
                try:
                    stats_dict_coleta['EquityCurve_JSON'] = stats_run_normal._equity_curve.to_json(
                        orient='split', date_format='iso')
                except Exception as e_json_eq_n:
                    print(
                        f"AVISO: Falha ao converter _equity_curve (normal) para JSON para {coin}: {e_json_eq_n}")
                    stats_dict_coleta['EquityCurve_JSON'] = None
            else:
                stats_dict_coleta['EquityCurve_JSON'] = None

            if hasattr(stats_run_normal, '_trades') and stats_run_normal._trades is not None and not stats_run_normal._trades.empty:
                try:
                    stats_dict_coleta['Trades_JSON'] = stats_run_normal._trades.to_json(
                        orient='split', date_format='iso')
                except Exception as e_json_tr_n:
                    print(
                        f"AVISO: Falha ao converter _trades (normal) para JSON para {coin}: {e_json_tr_n}")
                    stats_dict_coleta['Trades_JSON'] = None
            else:
                stats_dict_coleta['Trades_JSON'] = None
            # --- FIM DA MODIFICAÇÃO ---

            desc_parts_normal = [f"{k.replace('_otim','').upper()} {v:.0f}" if isinstance(
                v, int) else f"{k.replace('_otim','').upper()} {v:.2f}" for k, v in active_parameters_for_run_dict[coin].items()]
            descricao_final_para_db = f"Run Normal: {', '.join(desc_parts_normal)} | TF{timeframe}m, {days_history}d"

            stats_dict_coleta = stats_run_normal.to_dict()
            stats_dict_coleta['Asset'] = coin
            stats_dict_coleta['Otimizado'] = False
            stats_dict_coleta['Descricao_Estrategia'] = descricao_final_para_db[:250]
            all_stats_list_para_df_final.append(stats_dict_coleta)

        # --- E. Registro da Execução Principal (apenas uma vez por script) ---
        if DB_MANAGER_AVAILABLE and id_execucao_principal_script is None:
            otim_ranges_str = json.dumps({k: list(v) if isinstance(
                v, range) else v for k, v in params_otimizacao_ranges.items()})
            desc_exec_geral = (
                f"Script (Otim: {MODO_OTIMIZACAO}, Alvo: {METRICA_OTIMIZACAO if MODO_OTIMIZACAO else 'N/A'}) "
                # Limita o tamanho
                f"TF{timeframe}m, {days_history}d. OtimRanges: {str(otim_ranges_str)[:200]}"
            )
            # Usa os parâmetros do primeiro ativo processado para registrar na tabela Execucoes
            first_coin_params = active_parameters_for_run_dict.get(
                coins[0], {})
            params_db_exec = {
                'timeframe': timeframe, 'dias_historico': days_history,
                'lista_ativos': json.dumps(coins),
                'fast_ma_type': fast_ma_type_est_cfg,
                'fast_ma_length': int(first_coin_params.get('fast_ma_len_otim', EstrategiaMultiIndicador.fast_ma_len_otim)),
                'slow_ma_type': slow_ma_type_est_cfg,
                'slow_ma_length': int(first_coin_params.get('slow_ma_len_otim', EstrategiaMultiIndicador.slow_ma_len_otim)),
                'zonas_periodo': zonas_periodo_padrao,
                'vader_params': json.dumps(vader_params_padrao),
                'sl_percent': float(first_coin_params.get('sl_percent_otim', EstrategiaMultiIndicador.sl_percent_otim)),
                'tp_rr': float(first_coin_params.get('tp_rr_otim', EstrategiaMultiIndicador.tp_rr_otim)),
                'equity_fraction_per_trade': EstrategiaMultiIndicador.equity_fraction_per_trade,
                'initial_cash': initial_cash, 'commission_rate': commission_rate,
                'margin': margin_param, 'descricao': desc_exec_geral[:500]
            }
            id_execucao_principal_script = registrar_execucao(params_db_exec)
            if id_execucao_principal_script:
                print(
                    f"Execução Principal registrada no DB com ID: {id_execucao_principal_script}")
            else:
                print("Falha ao registrar execução principal no DB.")
                DB_MANAGER_AVAILABLE = False  # Desabilita salvamento se registro principal falhar

        # Adiciona o ID principal ao resultado do ativo atual, se ele foi criado nesta iteração
        if id_execucao_principal_script and all_stats_list_para_df_final and \
           (len(all_stats_list_para_df_final) > 0 and 'id_execucao_principal' not in all_stats_list_para_df_final[-1]):
            all_stats_list_para_df_final[-1]['id_execucao_principal'] = id_execucao_principal_script

        print(f"Processamento para {coin} concluído.")

    # --- F. Tratamento de Erros Críticos por Ativo ---
    except Exception as e_outer:
        print(
            f"!!!!!!!! ERRO CRÍTICO ao processar {coin}: {type(e_outer).__name__} - {e_outer} !!!!!!!!")
        traceback.print_exc()
        # Registra o erro na lista de resultados
        stats_erro = {'Asset': coin, '# Trades': -1, 'Return [%]': np.nan,
                      'Otimizado': MODO_OTIMIZACAO,
                      'Descricao_Estrategia': f'Erro Crítico: {type(e_outer).__name__} - {str(e_outer)[:100]}'}
        if id_execucao_principal_script:  # Tenta adicionar o ID se já foi criado
            stats_erro['id_execucao_principal'] = id_execucao_principal_script
        all_stats_list_para_df_final.append(stats_erro)

# --------------------------------------------------
# 3. Salvar Resultados Válidos no Banco de Dados
# --------------------------------------------------
resultados_para_salvar_no_db = []
id_exec_para_salvar = None

# Encontra o ID da execução principal válido na lista de resultados
for entry in all_stats_list_para_df_final:
    if 'id_execucao_principal' in entry and entry['id_execucao_principal'] is not None:
        id_exec_para_salvar = entry['id_execucao_principal']
        break

# Procede apenas se um ID válido foi encontrado e o DB está disponível
if DB_MANAGER_AVAILABLE and id_exec_para_salvar:
    for stat_entry in all_stats_list_para_df_final:
        # Pula entradas que são erros de processamento
        if stat_entry.get('# Trades', -1) == -1:
            continue

        # Garante que a entrada tem o ID da execução principal
        stat_entry['id_execucao_principal'] = id_exec_para_salvar

        teve_trades = stat_entry.get('# Trades', 0) > 0

        # Define se deve salvar baseado no modo e na flag SALVAR_RESULTADOS_OTIMIZADOS_NO_DB
        salvar_otimizado = stat_entry.get(
            'Otimizado', False) and SALVAR_RESULTADOS_OTIMIZADOS_NO_DB
        salvar_normal = not stat_entry.get('Otimizado', False)

        # Só salva se for um run normal com trades OU um run otimizado com trades (e a flag permite)
        if (salvar_normal or salvar_otimizado) and teve_trades:
            db_entry = stat_entry.copy()
            db_entry['Foi_Otimizado'] = stat_entry.get('Otimizado', False)
            db_entry['Estrategia_Descricao'] = stat_entry.get(
                'Descricao_Estrategia', 'N/A')[:250]
            resultados_para_salvar_no_db.append(db_entry)

    # Se houver resultados válidos para salvar
    if resultados_para_salvar_no_db:
        print(
            f"\nRegistrando {len(resultados_para_salvar_no_db)} resultados de ativos no DB para Execução Principal ID: {id_exec_para_salvar}...")
        try:
            payload_formatado_db = []
            # Mapeamento explícito das chaves do dicionário de stats para as colunas do DB
            map_keys_to_db = {
                'Asset': 'Asset', 'Start': 'StartTime', 'End': 'EndTime', 'Duration': 'Duration',
                'Exposure Time [%]': 'Exposure_Time_Percent', 'Equity Final [$]': 'Equity_Final',
                'Equity Peak [$]': 'Equity_Peak', 'Return [%]': 'Return_Percent',
                'Buy & Hold Return [%]': 'Buy_Hold_Return_Percent', 'Return (Ann.) [%]': 'Return_Ann_Percent',
                'Volatility (Ann.) [%]': 'Volatility_Ann_Percent', 'Sharpe Ratio': 'Sharpe_Ratio',
                'Sortino Ratio': 'Sortino_Ratio', 'Calmar Ratio': 'Calmar_Ratio',
                'Max. Drawdown [%]': 'Max_Drawdown_Percent', 'Avg. Drawdown [%]': 'Avg_Drawdown_Percent',
                'Max. Drawdown Duration': 'Max_Drawdown_Duration', 'Avg. Drawdown Duration': 'Avg_Drawdown_Duration',
                '# Trades': 'Num_Trades', 'Win Rate [%]': 'Win_Rate_Percent',
                'Best Trade [%]': 'Best_Trade_Percent', 'Worst Trade [%]': 'Worst_Trade_Percent',
                'Avg. Trade [%]': 'Avg. Trade_Percent', 'Max. Trade Duration': 'Max_Trade_Duration',
                'Avg. Trade Duration': 'Avg_Trade_Duration', 'Profit Factor': 'Profit_Factor',
                'Expectancy [%]': 'Expectancy_Percent', 'SQN': 'SQN',
                # Coluna existe na tabela? (garantido por salvar_colunas.py)
                'Foi_Otimizado': 'Foi_Otimizado',
                'Estrategia_Descricao': 'Estrategia_Descricao',  # Coluna existe na tabela?
                'EquityCurve_JSON': 'EquityCurve_JSON',          # Nova coluna para dados JSON
                'Trades_JSON': 'Trades_JSON'                      # Nova coluna para dados JSON
            }
            for res_original in resultados_para_salvar_no_db:
                # Inicia com a chave estrangeira
                item_db = {'id_execucao': id_exec_para_salvar}
                for script_key, db_key in map_keys_to_db.items():
                    if script_key in res_original:
                        value = res_original[script_key]
                        # Tratamento de tipos para SQLite
                        if isinstance(value, (pd.Timedelta, pd.Timestamp, pd.Period)):
                            value = str(value)
                        elif pd.isna(value) or value == np.inf or value == -np.inf:
                            value = None  # Trata NaN e Infinito
                        elif isinstance(value, np.integer):
                            value = int(value)
                        elif isinstance(value, np.floating):
                            value = float(value)
                        elif isinstance(value, np.bool_):
                            value = bool(value)
                        elif isinstance(value, bool):
                            value = bool(value)
                        item_db[db_key] = value

                # Adiciona o nome da estratégia
                if '_strategy' in res_original:
                    strat_val = res_original['_strategy']
                    if hasattr(strat_val, '__name__'):
                        item_db['_strategy'] = strat_val.__name__
                    else:
                        item_db['_strategy'] = str(strat_val)[:250]
                elif 'Estrategia_Descricao' in item_db:
                    item_db['_strategy'] = item_db['Estrategia_Descricao'][:100]
                else:
                    item_db['_strategy'] = EstrategiaMultiIndicador.__name__

                payload_formatado_db.append(item_db)

            # Envia o payload formatado para a função de registro no DB
            if payload_formatado_db:
                registrar_resultados_ativos(
                    id_exec_para_salvar, payload_formatado_db)
                print("Resultados dos ativos registrados no banco de dados.")
            else:
                print("Nenhum payload válido preparado para o banco de dados.")

        except Exception as e_db_reg:
            print(
                f"ERRO ao preparar ou registrar resultados de ativos no DB: {type(e_db_reg).__name__} - {e_db_reg}")
            traceback.print_exc()
    elif DB_MANAGER_AVAILABLE and id_exec_para_salvar:
        print("Nenhum resultado de ativo com trades > 0 para salvar no DB nesta execução.")
elif not DB_MANAGER_AVAILABLE:
    print("Banco de dados não disponível, resultados não foram salvos.")
else:  # DB disponível, mas nenhum id_exec_para_salvar foi encontrado
    # Se houve algum resultado não-erro
    if any(s.get('# Trades', -1) != -1 for s in all_stats_list_para_df_final):
        print("AVISO: Nenhum ID de execução principal válido foi encontrado. Resultados dos ativos não serão salvos.")


# --------------------------------------------------
# 4. Apresentar Resultados Consolidados na Tela
# --------------------------------------------------
print(f"\n\n{'='*20} RESULTADO CONSOLIDADO DO SCRIPT {'='*20}")
if all_stats_list_para_df_final:
    results_df = pd.DataFrame(all_stats_list_para_df_final)
    # Filtra entradas que são apenas erros de processamento
    results_df_validos = results_df[results_df['# Trades'] != -1].copy()

    if not results_df_validos.empty:
        # Define as colunas a serem exibidas no console
        cols_display_console = ['Asset', 'Otimizado', 'Return [%]', METRICA_OTIMIZACAO if MODO_OTIMIZACAO else 'Sharpe Ratio',
                                '# Trades', 'Win Rate [%]', 'Max. Drawdown [%]', 'Descricao_Estrategia']
        # Garante que só colunas existentes sejam selecionadas
        cols_existentes_no_df = [
            c for c in cols_display_console if c in results_df_validos.columns]

        # Cria mapa de formatação para floats
        float_format_map = {
            'Return [%]': '{:.2f}%'.format,
            METRICA_OTIMIZACAO: '{:.2f}'.format if MODO_OTIMIZACAO else None,
            'Sharpe Ratio': '{:.2f}'.format,
            'Sortino Ratio': '{:.2f}'.format,
            'Calmar Ratio': '{:.2f}'.format,
            'Win Rate [%]': '{:.2f}%'.format,
            'Max. Drawdown [%]': '{:.2f}%'.format
        }
        # Limpa o mapa de formatação (remove None e chaves que não existem no DF)
        float_format_map_clean = {k: v for k, v in float_format_map.items()
                                  if v is not None and k in results_df_validos.columns}

        # Imprime o DataFrame formatado
        try:
            print(results_df_validos[cols_existentes_no_df].to_string(index=False,
                                                                      formatters=float_format_map_clean if float_format_map_clean else None,
                                                                      na_rep='N/A'))
        except Exception as e_print:
            print(
                f"Erro ao formatar resultados para impressão: {e_print}. Imprimindo sem formatação:")
            print(results_df_validos[cols_existentes_no_df].to_string(
                index=False, na_rep='N/A'))

        # --- CHAMADA PARA PLOTAGEM (OPCIONAL - MATPLOTLIB) ---
        # Descomente as linhas abaixo se quiser gráficos gerados automaticamente aqui
        # if not results_df_validos.empty and any(results_df_validos.get('# Trades', pd.Series(0)) > 0):
        #     print("\nGerando visualizações (matplotlib)...")
        #     try:
        #         from visualizacao_resultados import gerar_visualizacoes
        #         gerar_visualizacoes(results_df_validos.copy())
        #     except ImportError:
        #         print("AVISO: visualizacao_resultados.py não encontrado. Gráficos matplotlib não serão gerados.")
        #     except Exception as e_plot:
        #         print(f"Erro ao gerar visualizações matplotlib: {e_plot}")
        #         traceback.print_exc()
        # elif not results_df_validos.empty:
        #      print("\nNenhum trade realizado nos resultados válidos. Gráficos matplotlib não serão gerados.")
    else:
        print("Nenhum resultado válido (sem erros de processamento) para exibir.")
        # Imprime os erros se houver
        erros_df = results_df[results_df['# Trades'] == -1]
        if not erros_df.empty:
            print("\n--- Erros de Processamento Encontrados ---")
            print(erros_df[['Asset', 'Descricao_Estrategia']
                           ].to_string(index=False))

else:
    print("Nenhum resultado final coletado para exibir.")

print(
    f"\nExecução do backtester.py (Otimização: {MODO_OTIMIZACAO}) concluída.")
