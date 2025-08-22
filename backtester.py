# backtester.py (Versão Final Otimizada e Refinada)

import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
from datetime import datetime, timezone, timedelta
import json
import traceback
import os
import traceback
import json
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

# --- Importações de Módulos Locais ---
import config  # Importa o novo arquivo de configuração
from bybit_data import fetch_bybit_kline
from indicadores import (calcular_atr, calcular_sentimento_vader,
                         calcular_zonas_compra_venda, ema, hma, sma, wma)

# Tenta importar o gerenciador de banco de dados
try:
    from database_manager import registrar_execucao, registrar_resultados_ativos
    DB_MANAGER_AVAILABLE = True
except ImportError:
    DB_MANAGER_AVAILABLE = False
    print("AVISO: database_manager.py não encontrado. Os resultados não serão salvos no banco de dados.")


# --- Classe da Estratégia ---
class EstrategiaMultiIndicador(Strategy):
    """
    Estratégia que combina cruzamento de Médias Móveis (otimizável),
    Zonas de Compra/Venda (fixo) e VADER (fixo) para gerar sinais.
    SL e TP também são otimizáveis.
    """
    # --- Parâmetros Otimizáveis (com valores padrão que serão usados se MODO_OTIMIZACAO=False) ---
    # Os valores padrão são carregados do arquivo de configuração
    fast_ma_len_otim = config.PARAMETROS_PADRAO['fast_ma_len_otim']
    slow_ma_len_otim = config.PARAMETROS_PADRAO['slow_ma_len_otim']
    multiplicador_sl_atr = config.PARAMETROS_PADRAO['multiplicador_sl_atr']
    tp_rr_otim = config.PARAMETROS_PADRAO['tp_rr_otim']

    # --- Parâmetros de Configuração Fixos (lidos do config) ---
    fast_ma_type_est = config.FAST_MA_TYPE
    slow_ma_type_est = config.SLOW_MA_TYPE
    equity_fraction_per_trade = config.EQUITY_FRACTION_PER_TRADE
    asset_name_param = "N/A_Asset"  # Nome do ativo (passado como parâmetro em tempo de execução)
    max_workers = None  # Parâmetro dummy exigido pela biblioteca ao passar 'max_workers' para otimização

    def init(self):
        """
        Inicializa a estratégia: calcula MAs (com params otimizáveis) e prepara séries de sinais.
        Indicadores Zonas, Vader e ATR são pré-calculados e acessados via self.data.
        """
        current_index = pd.to_datetime(self.data.index)
        close_series = pd.Series(self.data.Close, index=current_index)

        # Acessa o ATR pré-calculado
        self.atr_series_pd = pd.Series(self.data.ATR_I, index=current_index)

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
        self.sl_multiplicador_final = float(self.multiplicador_sl_atr)
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
        current_time_idx = self.data.index[-1]

        # --- LÓGICA DE SAÍDA POR INDICADOR ---
        # Se uma posição estiver aberta, avalia se devemos fechá-la com base em um sinal contrário.
        if self.position:
            # Se a posição for de COMPRA, um sinal de VENDA das MMs fecha a posição.
            if self.position.is_long and self.sinal_venda_mm_series[current_time_idx]:
                self.position.close()
                return  # Sai do método `next` para esta vela, pois a ação foi fechar.

            # Se a posição for de VENDA, um sinal de COMPRA das MMs fecha a posição.
            elif self.position.is_short and self.sinal_compra_mm_series[current_time_idx]:
                self.position.close()
                return

        # --- LÓGICA DE ENTRADA ---
        # Se o código chegou aqui, significa que não há posição aberta.
        # A lógica de entrada só é avaliada se não tivermos uma posição.
        if not self.position:
            try:
                sinal_compra_a_atual = self.compra_a_series[current_time_idx]
                sinal_venda_a_atual = self.venda_a_series[current_time_idx]
                sinal_compra_b_atual = self.compra_b_series[current_time_idx]
                sinal_venda_b_atual = self.venda_b_series[current_time_idx]
            except KeyError:
                return  # Pula a vela se o índice não for encontrado

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
                    distancia_sl = self.atr_series_pd[current_time_idx] * self.sl_multiplicador_final
                    sl_price = preco_entrada - distancia_sl
                    tp_price = preco_entrada + (distancia_sl * self.tp_rr_final)
                    try:
                        self.buy(size=size_to_use, sl=sl_price, tp=tp_price)
                    except Exception as e_buy:
                        print(
                            f"AVISO BUY [{self.asset_name_param}]@{current_time_idx}: Falha - {type(e_buy).__name__}: {e_buy}")
                        pass

                # Executa a ordem de Venda
                elif entrada_venda:
                    distancia_sl = self.atr_series_pd[current_time_idx] * self.sl_multiplicador_final
                    sl_price = preco_entrada + distancia_sl
                    tp_price = preco_entrada - (distancia_sl * self.tp_rr_final)
                    try:
                        self.sell(size=size_to_use, sl=sl_price, tp=tp_price)
                    except Exception as e_sell:
                        print(
                            f"AVISO SELL [{self.asset_name_param}]@{current_time_idx}: Falha - {type(e_sell).__name__}: {e_sell}")
                        pass


# --------------------------------------------------
# Funções Auxiliares de Execução
# --------------------------------------------------

def prepare_data_for_asset(coin: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """Busca e prepara os dados de um ativo, incluindo o cálculo de todos os indicadores."""
    print(f"Buscando e preparando dados para {coin}...")
    df_raw = fetch_bybit_kline(symbol=coin, interval=config.TIMEFRAME,
                               start_time_dt=start_date, end_time_dt=end_date, category='linear')

    # Validação de dados mínimos
    min_len_ma_otim = 0
    if config.MODO_OTIMIZACAO and config.RANGES_OTIMIZACAO.get('slow_ma_len_otim'):
        min_len_ma_otim = max(config.RANGES_OTIMIZACAO['slow_ma_len_otim'])
    min_candles_necessarias = max(
        config.ZONAS_PERIODO,
        config.VADER_PARAMS.get('vlookbk', 20),
        min_len_ma_otim,
        EstrategiaMultiIndicador.slow_ma_len_otim
    ) + 50  # Folga

    if df_raw.empty or len(df_raw) < min_candles_necessarias:
        print(f"AVISO: Dados insuficientes para {coin} ({len(df_raw)} velas, precisa de ~{min_candles_necessarias}). Pulando...")
        return None

    # Preparação do DataFrame
    df_bt = df_raw.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
    df_bt.index = pd.to_datetime(df_bt.index)

    # Cálculo de Indicadores
    print(f"Calculando indicadores para {coin}...")
    df_bt = calcular_zonas_compra_venda(df_bt, high_col='High', low_col='Low', periodo=config.ZONAS_PERIODO)
    df_bt = calcular_sentimento_vader(df_bt, price_col='Close', vol_col='Volume', high_col='High', low_col='Low', **config.VADER_PARAMS)
    df_bt = calcular_atr(df_bt, periodo=14, high_col='High', low_col='Low', close_col='Close')

    # Mapeamento e Renomeação de Colunas
    zonas_map = {'Strong Buy': 2, 'Buy': 1, 'Neutral': 0, 'Sell': -1, 'Strong Sell': -2}
    df_bt['ZCV_Zona_Num_Map'] = df_bt['zcv_zona'].map(zonas_map).fillna(0)
    df_bt.rename(columns={
        'ZCV_Zona_Num_Map': 'ZCV_Zona_Num_I',
        'vader_signal': 'VADER_Signal_I',
        'ATR_14': 'ATR_I'
    }, inplace=True)

    # Limpeza final
    colunas_essenciais = ['Open', 'High', 'Low', 'Close', 'Volume', 'ZCV_Zona_Num_I', 'VADER_Signal_I', 'ATR_I']
    df_bt.dropna(subset=colunas_essenciais, inplace=True)

    if df_bt.empty:
        print(f"AVISO: DataFrame para {coin} ficou VAZIO após limpeza. Pulando...")
        return None

    print(f"Dados para {coin} preparados: {len(df_bt)} velas.")
    return df_bt[colunas_essenciais].copy()

def run_backtest_or_optimize(df: pd.DataFrame, coin: str):
    """Executa o backtest ou a otimização para um único ativo."""
    bt = Backtest(df, EstrategiaMultiIndicador,
                  cash=config.INITIAL_CASH, commission=config.COMMISSION_RATE,
                  margin=config.MARGIN_PARAM, trade_on_close=True, exclusive_orders=True)

    params_para_rodada = {'asset_name_param': coin}

    if config.MODO_OTIMIZACAO:
        print(f"Rodando OTIMIZAÇÃO para {coin} | Alvo: {config.METRICA_OTIMIZACAO}...")
        valid_otim_params = {k: v for k, v in config.RANGES_OTIMIZACAO.items() if hasattr(EstrategiaMultiIndicador, k)}

        workers = config.MAX_WORKERS_OTIMIZACAO if config.MAX_WORKERS_OTIMIZACAO != -1 else os.cpu_count()
        print(f"Otimização com max_workers={workers}")

        stats, _ = bt.optimize(
            maximize=config.METRICA_OTIMIZACAO,
            return_heatmap=False,
            constraint=lambda p: p.fast_ma_len_otim < p.slow_ma_len_otim if hasattr(p, 'fast_ma_len_otim') and hasattr(p, 'slow_ma_len_otim') else True,
            max_workers=workers,
            **valid_otim_params,
            **params_para_rodada
        )

        print(f"Otimização para {coin} concluída.")
        if hasattr(stats, '_strategy'):
            melhores_params = {k: getattr(stats._strategy, k, None) for k in valid_otim_params.keys()}
            print("Rodando backtest final com parâmetros otimizados...")
            stats = bt.run(**melhores_params, **params_para_rodada)

            # Corrige o SyntaxError com f-string aninhada
            param_parts = []
            for k, v in melhores_params.items():
                if isinstance(v, float):
                    param_parts.append(f"{k.replace('_otim','').upper()} {v:.2f}")
                else:
                    param_parts.append(f"{k.replace('_otim','').upper()} {v}")
            params_str = ', '.join(param_parts)
            stats['Descricao_Estrategia'] = f"Otim ({config.METRICA_OTIMIZACAO[:4]}): {params_str}"
        else:
            stats['Descricao_Estrategia'] = f"Otim ({config.METRICA_OTIMIZACAO[:4]}) - Falha"

        stats['Otimizado'] = True
        return stats.to_dict(), melhores_params

    else: # Modo Backtest Padrão
        print(f"Rodando backtest PADRÃO para {coin}...")
        run_params = {**config.PARAMETROS_PADRAO, **params_para_rodada}
        stats = bt.run(**run_params)

        # Corrige o SyntaxError com f-string aninhada
        param_parts = []
        for k, v in config.PARAMETROS_PADRAO.items():
            if isinstance(v, float):
                param_parts.append(f"{k.replace('_otim','').upper()} {v:.2f}")
            else:
                param_parts.append(f"{k.replace('_otim','').upper()} {v}")
        params_str = ', '.join(param_parts)
        stats['Descricao_Estrategia'] = f"Run Normal: {params_str}"

        stats['Otimizado'] = False
        return stats.to_dict(), config.PARAMETROS_PADRAO

def main():
    """Função principal que orquestra todo o processo de backtesting."""
    start_time = datetime.now()
    end_date_dt = datetime.now(timezone.utc)
    start_date_dt = end_date_dt - timedelta(days=config.DIAS_HISTORICO)

    print("--- INICIANDO SCRIPT DE BACKTEST ---")
    print(f"Modo Otimização: {config.MODO_OTIMIZACAO}")
    print(f"Período: {start_date_dt.strftime('%Y-%m-%d')} a {end_date_dt.strftime('%Y-%m-%d')}")

    all_stats_list = []
    active_parameters = {}
    id_execucao = None

    for coin in config.COINS:
        print(f"\n{'='*20} Processando {coin} {'='*20}")
        try:
            df_asset = prepare_data_for_asset(coin, start_date_dt, end_date_dt)
            if df_asset is None:
                all_stats_list.append({'Asset': coin, '# Trades': -1, 'Descricao_Estrategia': 'Dados Insuficientes ou Erro na Preparação'})
                continue

            stats_dict, params_usados = run_backtest_or_optimize(df_asset, coin)
            stats_dict['Asset'] = coin
            active_parameters[coin] = params_usados
            all_stats_list.append(stats_dict)

            # Registro no DB (apenas uma vez)
            if DB_MANAGER_AVAILABLE and id_execucao is None and active_parameters:
                first_coin_params = next(iter(active_parameters.values()))
                params_db = {
                    'timeframe': config.TIMEFRAME, 'dias_historico': config.DIAS_HISTORICO,
                    'lista_ativos': json.dumps(config.COINS),
                    'fast_ma_type': config.FAST_MA_TYPE, 'slow_ma_type': config.SLOW_MA_TYPE,
                    'zonas_periodo': config.ZONAS_PERIODO, 'vader_params': json.dumps(config.VADER_PARAMS),
                    'sl_percent': float(first_coin_params.get('multiplicador_sl_atr', 0)),
                    'tp_rr': float(first_coin_params.get('tp_rr_otim', 0)),
                    'equity_fraction_per_trade': config.EQUITY_FRACTION_PER_TRADE,
                    'initial_cash': config.INITIAL_CASH, 'commission_rate': config.COMMISSION_RATE,
                    'margin': config.MARGIN_PARAM, 'descricao': f"Otim: {config.MODO_OTIMIZACAO}, Alvo: {config.METRICA_OTIMIZACAO if config.MODO_OTIMIZACAO else 'N/A'}"
                }
                id_execucao = registrar_execucao(params_db)
                if id_execucao:
                    print(f"Execução Principal registrada no DB com ID: {id_execucao}")
                else:
                    print("ERRO: Falha ao registrar execução principal no DB.")
                    # Poderia desabilitar o DB para o resto da execução

        except Exception as e:
            print(f"!!!!!!!! ERRO CRÍTICO ao processar {coin}: {e} !!!!!!!!")
            traceback.print_exc()
            all_stats_list.append({'Asset': coin, '# Trades': -1, 'Descricao_Estrategia': f'Erro Crítico: {e}'})

    # Salvar resultados no DB
    if DB_MANAGER_AVAILABLE and id_execucao and all_stats_list:
        valid_results_to_save = [s for s in all_stats_list if s.get('# Trades', -1) > 0]
        if valid_results_to_save:
            print(f"\nRegistrando {len(valid_results_to_save)} resultados de ativos no DB...")
            registrar_resultados_ativos(id_execucao, valid_results_to_save)
            print("Resultados salvos.")
        else:
            print("\nNenhum resultado com trades para salvar no DB.")

    # Apresentar resultados na tela
    print(f"\n--- RESULTADO CONSOLIDADO (Execução levou: {datetime.now() - start_time}) ---")
    if all_stats_list:
        results_df = pd.DataFrame(all_stats_list)
        cols_display = ['Asset', 'Otimizado', 'Return [%]', config.METRICA_OTIMIZACAO if config.MODO_OTIMIZACAO else 'Sharpe Ratio',
                        '# Trades', 'Win Rate [%]', 'Max. Drawdown [%]', 'Descricao_Estrategia']
        cols_existentes = [c for c in cols_display if c in results_df.columns]
        print(results_df[cols_existentes].to_string(index=False, na_rep='N/A'))
    else:
        print("Nenhum resultado final foi gerado.")

    print(f"\n--- Execução do backtester.py concluída. ---")

if __name__ == '__main__':
    main()
