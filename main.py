import matplotlib # <--- Adicionar esta linha
matplotlib.use('TkAgg') # <--- Adicionar esta linha (Define o backend)
import pandas as pd
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt # <--- IMPORTANTE: Adicionar esta linha

# --- Importar suas funções dos outros arquivos ---
from bybit_data import fetch_bybit_kline
from indicadores import calcular_ondas_alta_baixa, calcular_zonas_compra_venda, calcular_sentimento_vader # <--- Adicionar nova função aqui


# --------------------------------------------------
# Nova Função para Plotar o Gráfico
# --------------------------------------------------


# ==============================================
# --- BLOCO PRINCIPAL DE EXECUÇÃO (main.py) ---
# ==============================================

if __name__ == "__main__":

    # --- Definição dos Parâmetros ---
    # (Mantenha seus parâmetros aqui)
    symbol_to_fetch = 'SUIUSDT'
    interval_to_fetch = '3' # Testando com 15 min novamente
    category_to_fetch = 'linear'
    end_date = datetime.now(timezone.utc)
    # Lembre-se de verificar o relógio do sistema!
    start_date = end_date - timedelta(days=10) # Período de 10 dias
    fast_ma_config = {'type': 'EMA', 'length': 13}
    slow_ma_config = {'type': 'SMA', 'length': 34}
    zonas_periodo_config = 1500
    vader_params = {
        'length': 10, 'der_avg': 5, 'ma_type': 'WMA', 'smooth': 3,
        'show_senti': True, 'senti_len': 20, 'v_calc': 'Relative', 'vlookbk': 20
    }
    # -----------------------------------

    print(f"Período selecionado: {start_date} a {end_date}")

    # --- Busca de Dados ---
    print(f"\nIniciando busca de dados para {symbol_to_fetch} ({interval_to_fetch})...")
    df_dados = fetch_bybit_kline(
        category=category_to_fetch,
        symbol=symbol_to_fetch,
        interval=interval_to_fetch,
        start_time_dt=start_date,
        end_time_dt=end_date
    )

    # --- Cálculo dos Indicadores ---
    df_final = pd.DataFrame()
    if not df_dados.empty:
        print("\nCalculando indicadores...")
        # (Cálculo dos 3 indicadores como antes)
        df_calc = df_dados.copy()
        df_calc = calcular_ondas_alta_baixa(
            df_calc,
            fast_ma_type=fast_ma_config['type'], fast_ma_length=fast_ma_config['length'],
            slow_ma_type=slow_ma_config['type'], slow_ma_length=slow_ma_config['length']
        )
        df_calc = calcular_zonas_compra_venda(
            df_calc, periodo=zonas_periodo_config
        )
        df_calc = calcular_sentimento_vader(
             df_calc, **vader_params
        )
        df_final = df_calc


        # --- INÍCIO: Cálculo das Regras de Estratégia Combinada (A e B) ---
        print("\nCalculando regras de estratégia combinada (A e B)...")

        # Condições Individuais (Revisão)
        condicao_ondas_compra = df_final['sinal_compra'] == True
        condicao_zonas_compra = df_final['zcv_zona'].isin(['Buy', 'Strong Buy'])
        condicao_vader_positivo = df_final['vader_signal'] > 0
        condicao_vader_cruzou_zero_up = (df_final['vader_signal'] > 0) & (df_final['vader_signal'].shift(1) <= 0)

        condicao_ondas_venda = df_final['sinal_venda'] == True
        condicao_zonas_venda = df_final['zcv_zona'].isin(['Sell', 'Strong Sell'])
        condicao_vader_negativo = df_final['vader_signal'] < 0
        condicao_vader_cruzou_zero_down = (df_final['vader_signal'] < 0) & (df_final['vader_signal'].shift(1) >= 0)

        # --- Criando Colunas SEPARADAS para Estratégia A e B ---
        df_final['COMPRA_A'] = (condicao_ondas_compra & condicao_zonas_compra & condicao_vader_positivo)
        df_final['VENDA_A'] = (condicao_ondas_venda & condicao_zonas_venda & condicao_vader_negativo)

        df_final['COMPRA_B'] = (condicao_ondas_compra & condicao_zonas_compra & condicao_vader_cruzou_zero_up)
        df_final['VENDA_B'] = (condicao_ondas_venda & condicao_zonas_venda & condicao_vader_cruzou_zero_down)
        # ---------------------------------------------------------

        print("Regras A e B calculadas.")
        # --- FIM: Cálculo das Regras de Estratégia ---

        print("\nResultado final do cálculo (últimas 5 linhas com estratégias A e B):")
        cols_to_show = ['close', 'zcv_zona', 'vader_signal', 'COMPRA_A', 'VENDA_A', 'COMPRA_B', 'VENDA_B']
        print(df_final[[col for col in cols_to_show if col in df_final.columns]].tail())


    # --- Plotagem com Subplots ---
    if not df_final.empty:
        print("\nGerando gráfico com múltiplos painéis e sinais das estratégias A e B...")
        try:
            # --- Criar Figura e Eixos ---
            fig, axes = plt.subplots(2, 1, sharex=True, figsize=(16, 10), gridspec_kw={'height_ratios': [3, 1]})
            fig.suptitle(f'Indicadores & Estratégias A/B - {symbol_to_fetch} ({interval_to_fetch})', fontsize=14)

            # --- Eixo 0: Preço, Ondas, Zonas C/V e SINAIS FINAIS (A e B) ---
            ax_price = axes[0]
            ax_price.set_ylabel("Preço / Zonas")
            # (Plotagem Zonas, Preço, MAs - igual a antes)
            ax_price.fill_between(df_final.index, df_final['zcv_0'], df_final['zcv_236'], color='palegreen', alpha=0.3, label='_nolegend_')
            ax_price.fill_between(df_final.index, df_final['zcv_236'], df_final['zcv_1000'], color='lightgreen', alpha=0.2, label='_nolegend_') #renomeei para zcv_1000 para evitar confusão com zcv_100
            ax_price.fill_between(df_final.index, df_final['zcv_618'], df_final['zcv_786'], color='lightcoral', alpha=0.2, label='_nolegend_')
            ax_price.fill_between(df_final.index, df_final['zcv_786'], df_final['zcv_100'], color='indianred', alpha=0.3, label='_nolegend_')
            ax_price.plot(df_final.index, df_final['close'], label='Preço', color='black', alpha=0.8, linewidth=1)
            ax_price.plot(df_final.index, df_final['slow_ma'], label=f"MA Lenta ({slow_ma_config['type']}{slow_ma_config['length']})", color='blue', linewidth=1.5, linestyle=':')
            ax_price.plot(df_final.index, df_final['fast_ma'], label=f"MA Rápida ({fast_ma_config['type']}{fast_ma_config['length']})", color='cyan', linewidth=1.5)


            # --- Plotar SINAIS FINAIS da Estratégia A (Círculos 'o') ---
            buy_A_signals = df_final[df_final['COMPRA_A']]
            if not buy_A_signals.empty:
                ax_price.plot(buy_A_signals.index, df_final.loc[buy_A_signals.index]['low'] * 0.985, # Posição A
                              'o', markersize=9, color='lime', label='COMPRA A (Vader>0)',
                              lw=0, markeredgecolor='black', alpha=0.8)
            sell_A_signals = df_final[df_final['VENDA_A']]
            if not sell_A_signals.empty:
                 ax_price.plot(sell_A_signals.index, df_final.loc[sell_A_signals.index]['high'] * 1.015, # Posição A
                               'o', markersize=9, color='red', label='VENDA A (Vader<0)',
                               lw=0, markeredgecolor='black', alpha=0.8)
            # ---------------------------------------------

            # --- Plotar SINAIS FINAIS da Estratégia B (Estrelas '*') ---
            buy_B_signals = df_final[df_final['COMPRA_B']]
            if not buy_B_signals.empty:
                ax_price.plot(buy_B_signals.index, df_final.loc[buy_B_signals.index]['low'] * 0.975, # Posição B (ligeiramente diferente)
                              '*', markersize=11, color='greenyellow', label='COMPRA B (VaderX0↑)',
                              lw=0, markeredgecolor='black', alpha=0.9)
            sell_B_signals = df_final[df_final['VENDA_B']]
            if not sell_B_signals.empty:
                 ax_price.plot(sell_B_signals.index, df_final.loc[sell_B_signals.index]['high'] * 1.025, # Posição B (ligeiramente diferente)
                               '*', markersize=11, color='deeppink', label='VENDA B (VaderX0↓)',
                               lw=0, markeredgecolor='black', alpha=0.9)
            # ---------------------------------------------

            ax_price.legend(loc='upper left', fontsize='xx-small') # Legenda ainda menor
            ax_price.grid(True, linestyle='--', alpha=0.4)

            # --- Eixo 1: VADER ---
            # (Plotagem do VADER continua igual)
            ax_vader = axes[1]
            ax_vader.set_ylabel("VADER Sentimento")
            # ... (código plotagem VADER) ...
            ax_vader.plot(df_final.index, df_final['vader_adp'], label='Demanda (ADP)', color='aqua', linewidth=1, alpha=0.7)
            ax_vader.plot(df_final.index, df_final['vader_asp'], label='Oferta (ASP)', color='orange', linewidth=1, alpha=0.7)
            ax_vader.fill_between(df_final.index, df_final['vader_adp'], df_final['vader_asp'], where=df_final['vader_adp'] >= df_final['vader_asp'], color='green', alpha=0.2, interpolate=True, label='_nolegend_')
            ax_vader.fill_between(df_final.index, df_final['vader_adp'], df_final['vader_asp'], where=df_final['vader_adp'] < df_final['vader_asp'], color='red', alpha=0.2, interpolate=True, label='_nolegend_')
            ax_vader.plot(df_final.index, df_final['vader_signal'], label='Sinal VADER', color='blue', linewidth=2, alpha=0.8)
            if vader_params['show_senti'] and 'vader_sentiment' in df_final and not df_final['vader_sentiment'].isnull().all():
                 ax_vader.plot(df_final.index, df_final['vader_sentiment'], label='Sentimento Longo Prazo', color='purple', linestyle=':', linewidth=1.5, alpha=0.7)
            ax_vader.axhline(0, color='grey', linestyle='--', linewidth=1)
            ax_vader.legend(loc='upper left', fontsize='x-small')
            ax_vader.grid(True, linestyle='--', alpha=0.4)


            # --- Finalizar e Mostrar ---
            plt.tight_layout(rect=[0, 0, 1, 0.97])
            plt.show()
            print("Gráfico deve ter sido exibido.")

        except Exception as e:
            print(f"Ocorreu um erro ao gerar o gráfico: {e}")
            import traceback
            traceback.print_exc()

    else:
        print("\nNão foi possível obter dados da Bybit para calcular ou plotar.")

    print("\nExecução de main.py concluída.")