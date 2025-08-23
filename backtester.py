import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
from datetime import datetime, timezone, timedelta
import json
import os

# --- Importações de Módulos Locais ---
# Forçando a releitura do módulo
import config
from bybit_data import fetch_bybit_kline
from indicadores import (calcular_atr, calcular_sentimento_vader,
                         calcular_zonas_compra_venda, ema, hma, sma, wma, calcular_indicadores_talib)
from sentiment_data import fetch_fear_and_greed_index
from logger_config import logger

# Tenta importar o gerenciador de banco de dados
try:
    from database_manager import create_tables, registrar_execucao, registrar_resultados_ativos
    DB_MANAGER_AVAILABLE = True
except ImportError:
    DB_MANAGER_AVAILABLE = False
    logger.warning("database_manager.py não encontrado. Os resultados não serão salvos no banco de dados.")


# --- Classe da Estratégia ---
class EstrategiaMultiIndicador(Strategy):
    """
    Estratégia que combina cruzamento de Médias Móveis (otimizável),
    Zonas de Compra/Venda (fixo) e VADER (fixo) para gerar sinais.
    SL e TP também são otimizáveis.
    """
    fast_ma_len_otim = config.PARAMETROS_PADRAO['fast_ma_len_otim']
    slow_ma_len_otim = config.PARAMETROS_PADRAO['slow_ma_len_otim']
    multiplicador_sl_atr = config.PARAMETROS_PADRAO['multiplicador_sl_atr']
    tp_rr_otim = config.PARAMETROS_PADRAO['tp_rr_otim']

    fast_ma_type_est = config.FAST_MA_TYPE
    slow_ma_type_est = config.SLOW_MA_TYPE
    equity_fraction_per_trade = config.EQUITY_FRACTION_PER_TRADE
    asset_name_param = "N/A_Asset"
    max_workers = None

    def init(self):
        """
        Inicializa a estratégia: calcula MAs e prepara séries de sinais.
        """
        # Garante que os dados sejam Series do Pandas para operações vetoriais
        close_series = pd.Series(self.data.Close, index=self.data.index)

        # --- Cálculo das Médias Móveis (Ondas) ---
        ma_functions = {'SMA': sma, 'EMA': ema, 'WMA': wma, 'HMA': hma}
        try:
            func_ma_rapida = ma_functions[self.fast_ma_type_est]
            func_ma_lenta = ma_functions[self.slow_ma_type_est]
        except KeyError:
            raise ValueError(f"Tipo de MA inválido: Rápida ('{self.fast_ma_type_est}'), Lenta ('{self.slow_ma_type_est}')")

        fast_len = int(self.fast_ma_len_otim)
        slow_len = int(self.slow_ma_len_otim)
        ma_rapida_series = func_ma_rapida(close_series, fast_len)
        ma_lenta_series = func_ma_lenta(close_series, slow_len)

        sinal_compra_mm_series = (ma_rapida_series > ma_lenta_series) & (ma_rapida_series.shift(1) <= ma_lenta_series.shift(1))
        sinal_venda_mm_series = (ma_rapida_series < ma_lenta_series) & (ma_rapida_series.shift(1) >= ma_lenta_series.shift(1))

        # --- Condições de base dos indicadores ---
        cond_ondas_compra = sinal_compra_mm_series == True
        cond_zonas_compra = pd.Series(self.data.ZCV_Zona_Num_I, index=self.data.index).isin([1, 2])
        cond_vader_positivo = self.data.VADER_Signal_I > 0
        cond_vader_cruzou_zero_up = (self.data.VADER_Signal_I > 0) & (pd.Series(self.data.VADER_Signal_I, index=self.data.index).shift(1) <= 0)

        cond_ondas_venda = sinal_venda_mm_series == True
        cond_zonas_venda = pd.Series(self.data.ZCV_Zona_Num_I, index=self.data.index).isin([-1, -2])
        cond_vader_negativo = self.data.VADER_Signal_I < 0
        cond_vader_cruzou_zero_down = (self.data.VADER_Signal_I < 0) & (pd.Series(self.data.VADER_Signal_I, index=self.data.index).shift(1) >= 0)

        # --- FILTROS AVANÇADOS (CONFIGURÁVEIS) ---
        # Filtro de Regime de Mercado
        if config.USAR_FILTRO_REGIME_MERCADO:
            regime_ma = pd.Series(self.data.Regime_MA, index=self.data.index)
            cond_tendencia_alta = (close_series > regime_ma) | regime_ma.isna()
            cond_tendencia_baixa = (close_series < regime_ma) | regime_ma.isna()
        else:
            cond_tendencia_alta = cond_tendencia_baixa = pd.Series(True, index=self.data.index)

        # Filtro de Confirmação (Stochastic RSI)
        if config.USAR_FILTRO_STOCH_RSI:
            stoch_k = pd.Series(self.data.StochRSI_K, index=self.data.index)
            stoch_d = pd.Series(self.data.StochRSI_D, index=self.data.index)
            params = config.STOCH_RSI_FILTER_PARAMS
            cond_stoch_compra = (stoch_k > stoch_d) & (stoch_k.shift(1) <= stoch_d.shift(1)) & (stoch_k < params['limite_compra'])
            cond_stoch_venda = (stoch_k < stoch_d) & (stoch_k.shift(1) >= stoch_d.shift(1)) & (stoch_k > params['limite_venda'])
            cond_stoch_compra = cond_stoch_compra | stoch_k.isna()
            cond_stoch_venda = cond_stoch_venda | stoch_k.isna()
        else:
            cond_stoch_compra = cond_stoch_venda = pd.Series(True, index=self.data.index)

        # --- Lógica de Entrada Final com os Novos Filtros ---
        self.compra_a_series = (cond_ondas_compra & cond_zonas_compra & cond_vader_positivo & cond_tendencia_alta & cond_stoch_compra).fillna(False)
        self.venda_a_series = (cond_ondas_venda & cond_zonas_venda & cond_vader_negativo & cond_tendencia_baixa & cond_stoch_venda).fillna(False)
        self.compra_b_series = (cond_ondas_compra & cond_zonas_compra & cond_vader_cruzou_zero_up & cond_tendencia_alta & cond_stoch_compra).fillna(False)
        self.venda_b_series = (cond_ondas_venda & cond_zonas_venda & cond_vader_cruzou_zero_down & cond_tendencia_baixa & cond_stoch_venda).fillna(False)

        self.sl_multiplicador_final = float(self.multiplicador_sl_atr)
        self.tp_rr_final = float(self.tp_rr_otim)

        # --- Atributos para o método next() ---
        self.sinal_compra_mm_series = sinal_compra_mm_series
        self.sinal_venda_mm_series = sinal_venda_mm_series
        self.atr_series_pd = pd.Series(self.data.ATR_I, index=self.data.index)

    def next(self):
        """
        Método chamado para cada vela de dados. Verifica os sinais e executa ordens.
        """
        current_time_idx = self.data.index[-1]

        if self.position:
            if self.position.is_long and self.sinal_venda_mm_series[current_time_idx]:
                self.position.close()
                return
            elif self.position.is_short and self.sinal_compra_mm_series[current_time_idx]:
                self.position.close()
                return

        if not self.position:
            try:
                sinal_compra_a_atual = self.compra_a_series[current_time_idx]
                sinal_venda_a_atual = self.venda_a_series[current_time_idx]
                sinal_compra_b_atual = self.compra_b_series[current_time_idx]
                sinal_venda_b_atual = self.venda_b_series[current_time_idx]
            except KeyError:
                return

            entrada_compra = sinal_compra_a_atual or sinal_compra_b_atual
            entrada_venda = sinal_venda_a_atual or sinal_venda_b_atual

            if entrada_compra or entrada_venda:
                preco_entrada = self.data.Close[-1]
                size_to_use = self.equity_fraction_per_trade
                distancia_sl = self.atr_series_pd[current_time_idx] * self.sl_multiplicador_final

                if entrada_compra:
                    sl_price = preco_entrada - distancia_sl
                    tp_price = preco_entrada + (distancia_sl * self.tp_rr_final)
                    try:
                        self.buy(size=size_to_use, sl=sl_price, tp=tp_price)
                    except Exception as e_buy:
                        logger.warning(f"BUY Falhou [{self.asset_name_param}]@{current_time_idx}: {e_buy}")
                elif entrada_venda:
                    sl_price = preco_entrada + distancia_sl
                    tp_price = preco_entrada - (distancia_sl * self.tp_rr_final)
                    try:
                        self.sell(size=size_to_use, sl=sl_price, tp=tp_price)
                    except Exception as e_sell:
                        logger.warning(f"SELL Falhou [{self.asset_name_param}]@{current_time_idx}: {e_sell}")

# --------------------------------------------------
# Funções Auxiliares de Execução
# --------------------------------------------------

def prepare_data_for_asset(coin: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """Busca e prepara os dados de um ativo, incluindo o cálculo de todos os indicadores."""
    logger.info(f"Buscando e preparando dados para {coin}...")
    df_raw = fetch_bybit_kline(symbol=coin, interval=config.TIMEFRAME,
                               start_time_dt=start_date, end_time_dt=end_date, category='linear')

    min_len_ma_otim = 0
    if config.MODO_OTIMIZACAO and config.RANGES_OTIMIZACAO.get('slow_ma_len_otim'):
        min_len_ma_otim = max(config.RANGES_OTIMIZACAO['slow_ma_len_otim'])
    min_candles_necessarias = max(config.ZONAS_PERIODO, config.VADER_PARAMS.get('vlookbk', 20), min_len_ma_otim, EstrategiaMultiIndicador.slow_ma_len_otim) + 50

    if df_raw.empty or len(df_raw) < min_candles_necessarias:
        logger.warning(f"Dados insuficientes para {coin} ({len(df_raw)} velas, precisa de ~{min_candles_necessarias}). Pulando...")
        return None

    df_bt = df_raw.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
    df_bt.index = pd.to_datetime(df_bt.index)

    # Buscar e mesclar dados de sentimento (Fear & Greed)
    fng_data = fetch_fear_and_greed_index(limit=config.DIAS_HISTORICO + 5) # +5 dias de margem
    if not fng_data.empty:
        df_bt = pd.merge_asof(df_bt.sort_index(), fng_data.sort_index(), left_index=True, right_index=True, direction='backward')
        df_bt[['fng_value', 'fng_classification']] = df_bt[['fng_value', 'fng_classification']].ffill()

    # --- FILTRO DE REGIME DE MERCADO (OPCIONAL) ---
    regime_ma_col_name = 'Regime_MA'
    if config.USAR_FILTRO_REGIME_MERCADO:
        params = config.REGIME_FILTER_PARAMS
        logger.info(f"Buscando dados {params['timeframe']} para o filtro de tendência para {coin}...")
        start_date_regime_dt = end_date_dt - timedelta(days=config.DIAS_HISTORICO + 250)
        df_regime = fetch_bybit_kline(
            symbol=coin, interval=params['timeframe'],
            start_time_dt=start_date_regime_dt, end_time_dt=end_date_dt, category='linear'
        )
        ma_periodo = params['ma_periodo']
        if not df_regime.empty and len(df_regime) >= ma_periodo:
            df_regime[regime_ma_col_name] = ema(df_regime['close'], length=ma_periodo)
            df_regime_to_merge = df_regime[[regime_ma_col_name]].copy()
            df_bt = pd.merge_asof(
                left=df_bt.sort_index(), right=df_regime_to_merge.sort_index(),
                left_index=True, right_index=True, direction='backward'
            )
            df_bt[regime_ma_col_name] = df_bt[regime_ma_col_name].ffill()
            logger.info(f"Filtro de tendência (EMA {ma_periodo} {params['timeframe']}) mesclado.")
        else:
            logger.warning(f"Dados insuficientes para EMA {ma_periodo} em {coin}. Filtro de tendência desativado.")
            df_bt[regime_ma_col_name] = np.nan
    else:
        df_bt[regime_ma_col_name] = np.nan # Coluna vazia se filtro desativado
    # --- FIM FILTRO REGIME ---

    logger.info(f"Calculando indicadores para {coin}...")
    df_bt = calcular_zonas_compra_venda(df_bt, high_col='High', low_col='Low', close_col='Close', periodo=config.ZONAS_PERIODO)
    df_bt = calcular_sentimento_vader(df_bt, price_col='Close', vol_col='Volume', high_col='High', low_col='Low', **config.VADER_PARAMS)
    df_bt = calcular_atr(df_bt, periodo=config.ATR_PERIODO, high_col='High', low_col='Low', close_col='Close')

    stoch_params = config.STOCH_RSI_FILTER_PARAMS if config.USAR_FILTRO_STOCH_RSI else None
    df_bt = calcular_indicadores_talib(df_bt, stoch_rsi_params=stoch_params)

    zonas_map = {'Strong Buy': 2, 'Buy': 1, 'Neutral': 0, 'Sell': -1, 'Strong Sell': -2}
    df_bt['ZCV_Zona_Num_Map'] = df_bt['zcv_zona'].map(zonas_map).fillna(0)
    df_bt.rename(columns={'ZCV_Zona_Num_Map': 'ZCV_Zona_Num_I', 'vader_signal': 'VADER_Signal_I', f'ATR_{config.ATR_PERIODO}': 'ATR_I'}, inplace=True)

    colunas_core_para_dropna = ['Open', 'High', 'Low', 'Close', 'Volume', 'ZCV_Zona_Num_I', 'VADER_Signal_I', 'ATR_I', 'fng_value']
    df_bt.dropna(subset=colunas_core_para_dropna, inplace=True)

    if df_bt.empty:
        logger.warning(f"DataFrame para {coin} ficou VAZIO após limpeza dos indicadores principais. Pulando...")
        return None

    # Adiciona colunas opcionais à lista final se os filtros estiverem ativos
    colunas_finais = colunas_core_para_dropna + [regime_ma_col_name]
    if config.USAR_FILTRO_STOCH_RSI:
        colunas_finais.extend(['StochRSI_K', 'StochRSI_D'])

    # Garante que as colunas existam, mesmo que vazias, para evitar erros na estratégia
    for col in colunas_finais:
        if col not in df_bt.columns:
            df_bt[col] = np.nan

    logger.info(f"Dados para {coin} preparados: {len(df_bt)} velas.")
    colunas_existentes = [col for col in colunas_finais if col in df_bt.columns]
    return df_bt[colunas_existentes].copy()

def run_backtest_or_optimize(df: pd.DataFrame, coin: str):
    """Executa o backtest ou a otimização para um único ativo."""
    bt = Backtest(df, EstrategiaMultiIndicador, cash=config.INITIAL_CASH, commission=config.COMMISSION_RATE, margin=config.MARGIN_PARAM, trade_on_close=True, exclusive_orders=True)
    params_para_rodada = {'asset_name_param': coin}

    stats = None
    params_usados = {}

    if config.MODO_OTIMIZACAO:
        logger.info(f"Rodando OTIMIZAÇÃO para {coin} | Alvo: {config.METRICA_OTIMIZACAO}...")
        valid_otim_params = {k: v for k, v in config.RANGES_OTIMIZACAO.items() if hasattr(EstrategiaMultiIndicador, k)}
        workers = config.MAX_WORKERS_OTIMIZACAO if config.MAX_WORKERS_OTIMIZACAO != -1 else os.cpu_count()
        logger.info(f"Otimização com max_workers={workers}")

        stats_otimizacao = bt.optimize(
            maximize=config.METRICA_OTIMIZACAO, return_heatmap=False,
            constraint=lambda p: p.fast_ma_len_otim < p.slow_ma_len_otim if hasattr(p, 'fast_ma_len_otim') and hasattr(p, 'slow_ma_len_otim') else True,
            max_workers=workers, **valid_otim_params, **params_para_rodada
        )
        logger.info(f"Otimização para {coin} concluída.")

        if hasattr(stats_otimizacao, '_strategy'):
            params_usados = {k: getattr(stats_otimizacao._strategy, k, None) for k in valid_otim_params.keys()}
            logger.info("Rodando backtest final com parâmetros otimizados...")
            stats = bt.run(**params_usados, **params_para_rodada) # stats agora são do backtest final
            param_parts = [f"{k.replace('_otim','').upper()} {v:.2f}" if isinstance(v, float) else f"{k.replace('_otim','').upper()} {v}" for k, v in params_usados.items()]
            stats['Descricao_Estrategia'] = f"Otim ({config.METRICA_OTIMIZACAO[:4]}): {', '.join(param_parts)}"
            stats['Otimizado'] = True
        else:
            stats = stats_otimizacao # Se otimização falhou, usa as stats dela
            stats['Descricao_Estrategia'] = f"Otim ({config.METRICA_OTIMIZACAO[:4]}) - Falha"
            stats['Otimizado'] = True

    else: # Modo Backtest Padrão
        logger.info(f"Rodando backtest PADRÃO para {coin}...")
        params_usados = config.PARAMETROS_PADRAO
        stats = bt.run(**params_usados, **params_para_rodada)
        param_parts = [f"{k.replace('_otim','').upper()} {v:.2f}" if isinstance(v, float) else f"{k.replace('_otim','').upper()} {v}" for k, v in params_usados.items()]
        stats['Descricao_Estrategia'] = f"Run Normal: {', '.join(param_parts)}"
        stats['Otimizado'] = False

    # --- Processamento e retorno unificado ---
    if stats is not None:
        stats_dict = stats.to_dict()
        # Adiciona os dados de séries temporais ao dicionário para salvar no DB
        if hasattr(stats, '_equity_curve') and not stats['_equity_curve'].empty:
            stats_dict['EquityCurve_JSON'] = stats['_equity_curve'].to_json(orient='split', date_format='iso')
        if hasattr(stats, '_trades') and not stats['_trades'].empty:
            stats_dict['Trades_JSON'] = stats['_trades'].to_json(orient='split', date_format='iso')

        return stats_dict, params_usados
    else:
        return {}, {}

def main():
    """Função principal que orquestra todo o processo de backtesting."""
    if DB_MANAGER_AVAILABLE:
        create_tables()  # Garante que o DB e as tabelas existam antes de qualquer operação.

    start_time = datetime.now()
    end_date_dt = datetime.now(timezone.utc)
    start_date_dt = end_date_dt - timedelta(days=config.DIAS_HISTORICO)

    logger.info("--- INICIANDO SCRIPT DE BACKTEST ---")
    logger.info(f"Modo Otimização: {config.MODO_OTIMIZACAO}")
    logger.info(f"Período: {start_date_dt.strftime('%Y-%m-%d')} a {end_date_dt.strftime('%Y-%m-%d')}")

    all_stats_list = []
    active_parameters = {}
    id_execucao = None

    for coin in config.COINS:
        logger.info(f"{'='*20} Processando {coin} {'='*20}")
        try:
            df_asset = prepare_data_for_asset(coin, start_date_dt, end_date_dt)
            if df_asset is None:
                all_stats_list.append({'Asset': coin, '# Trades': -1, 'Descricao_Estrategia': 'Dados Insuficientes ou Erro na Preparação'})
                continue

            stats_dict, params_usados = run_backtest_or_optimize(df_asset, coin)
            stats_dict['Asset'] = coin
            active_parameters[coin] = params_usados
            all_stats_list.append(stats_dict)

            if DB_MANAGER_AVAILABLE and id_execucao is None and active_parameters:
                first_coin_params = next(iter(active_parameters.values()))
                params_db = {
                    'timeframe': config.TIMEFRAME, 'dias_historico': config.DIAS_HISTORICO,
                    'lista_ativos': json.dumps(config.COINS),
                    'fast_ma_type': config.FAST_MA_TYPE,
                    'slow_ma_type': config.SLOW_MA_TYPE,
                    'fast_ma_length': int(first_coin_params.get('fast_ma_len_otim', 0)),
                    'slow_ma_length': int(first_coin_params.get('slow_ma_len_otim', 0)),
                    'zonas_periodo': config.ZONAS_PERIODO,
                    'vader_params': json.dumps(config.VADER_PARAMS),
                    'sl_percent': float(first_coin_params.get('multiplicador_sl_atr', 0)),
                    'tp_rr': float(first_coin_params.get('tp_rr_otim', 0)),
                    'equity_fraction_per_trade': config.EQUITY_FRACTION_PER_TRADE,
                    'initial_cash': config.INITIAL_CASH,
                    'commission_rate': config.COMMISSION_RATE,
                    'margin': config.MARGIN_PARAM,
                    'descricao': f"Otim: {config.MODO_OTIMIZACAO}, Alvo: {config.METRICA_OTIMIZACAO if config.MODO_OTIMIZACAO else 'N/A'}"
                }
                id_execucao = registrar_execucao(params_db)
                if id_execucao:
                    logger.info(f"Execução Principal registrada no DB com ID: {id_execucao}")
                else:
                    logger.error("Falha ao registrar execução principal no DB.")

        except Exception as e:
            logger.critical(f"ERRO CRÍTICO ao processar {coin}: {e}", exc_info=True)
            all_stats_list.append({'Asset': coin, '# Trades': -1, 'Descricao_Estrategia': f'Erro Crítico: {e}'})

    if DB_MANAGER_AVAILABLE and id_execucao and all_stats_list:
        valid_results_to_save = [s for s in all_stats_list if s.get('# Trades', -1) > 0]
        if valid_results_to_save:
            logger.info(f"Registrando {len(valid_results_to_save)} resultados de ativos no DB...")
            registrar_resultados_ativos(id_execucao, valid_results_to_save)
            logger.info("Resultados salvos.")
        else:
            logger.info("Nenhum resultado com trades para salvar no DB.")

    logger.info(f"--- RESULTADO CONSOLIDADO (Execução levou: {datetime.now() - start_time}) ---")
    if all_stats_list:
        results_df = pd.DataFrame(all_stats_list)
        cols_display = ['Asset', 'Otimizado', 'Return [%]', config.METRICA_OTIMIZACAO if config.MODO_OTIMIZACAO else 'Sharpe Ratio',
                        '# Trades', 'Win Rate [%]', 'Max. Drawdown [%]', 'Descricao_Estrategia']
        cols_existentes = [c for c in cols_display if c in results_df.columns]
        # Usar logger.info para a tabela de resultados requer formatá-la primeiro
        results_string = results_df[cols_existentes].to_string(index=False, na_rep='N/A')
        logger.info(f"Resultados Finais:\n{results_string}")
    else:
        logger.info("Nenhum resultado final foi gerado.")

    logger.info(f"--- Execução do backtester.py concluída. ---")

if __name__ == '__main__':
    main()
