# visualizacao_resultados.py
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np # Adicionado para lidar com np.nan se necessário

def plotar_retorno_comparativo(df_resultados):
    """
    Gera um gráfico de barras comparando Retorno da Estratégia vs. Buy & Hold.
    """
    if df_resultados.empty:
        print("DataFrame de resultados vazio. Não é possível gerar o gráfico de retornos.")
        return

    df_plot = df_resultados.set_index('Asset')
    df_plot['Return [%]'] = df_plot['Return [%]'].fillna(0)
    df_plot['Buy & Hold Return [%]'] = df_plot['Buy & Hold Return [%]'].fillna(0)

    ax = df_plot[['Return [%]', 'Buy & Hold Return [%]']].plot(kind='bar', figsize=(15, 8), width=0.8) # Aumentei figsize e defini width
    plt.title('Comparativo: Retorno da Estratégia vs. Buy & Hold por Ativo', fontsize=16)
    plt.ylabel('Retorno (%)', fontsize=12)
    plt.xlabel('Ativo', fontsize=12)
    
    # Ajustar os xticklabels
    plt.xticks(rotation=45, ha="right", fontsize=10) # Adicionei fontsize
    
    plt.legend(["Retorno Estratégia", "Buy & Hold"], fontsize=10)
    plt.grid(axis='y', linestyle='--')

    # --- INÍCIO: Adicionar valores nas barras ---
    for p in ax.patches:
        width = p.get_width()
        height = p.get_height()
        x, y = p.get_xy()
        if height != 0: # Só adiciona texto se a barra não for zero
            ax.text(x + width/2,
                    y + height + (0.01 * height if height > 0 else -0.03 * abs(height) - 0.5), # Ajuste de posição
                    f"{height:.2f}%", # Formato do texto
                    ha='center',
                    va='bottom' if height > 0 else 'top', # Alinhamento vertical
                    fontsize=8, # Tamanho da fonte dos valores
                    color='black') # Cor do texto
    # --- FIM: Adicionar valores nas barras ---

    plt.tight_layout()
    plt.show()

def plotar_metricas_chave(df_resultados):
    """
    Gera gráficos de barras para Métricas Chave de Desempenho (Win Rate, # Trades, Max Drawdown).
    """
    if df_resultados.empty:
        print("DataFrame de resultados vazio. Não é possível gerar gráficos de métricas.")
        return

    df_plot_original = df_resultados.copy() # Mantém o original para diferentes ordenações

    metricas = ['Win Rate [%]', '# Trades', 'Max. Drawdown [%]']
    num_metricas = len(metricas)
    
    fig, axes = plt.subplots(nrows=num_metricas, ncols=1, figsize=(12, 6 * num_metricas), sharex=False) # Aumentei um pouco a altura por subplot
    if num_metricas == 1:
        axes = [axes]

    fig.suptitle('Métricas Chave de Desempenho por Ativo', fontsize=16)

    for i, metrica in enumerate(metricas):
        df_metrica_plot = df_plot_original.set_index('Asset')

        # Tratar NaNs e garantir tipos corretos
        if metrica not in df_metrica_plot.columns:
            print(f"Métrica '{metrica}' não encontrada no DataFrame. Pulando...")
            axes[i].text(0.5, 0.5, f"Métrica '{metrica}'\nnão disponível",
                         horizontalalignment='center', verticalalignment='center',
                         fontsize=12, color='red')
            axes[i].set_title(f"{metrica} (Não disponível)")
            axes[i].set_xlabel('Ativo' if i == num_metricas - 1 else '')
            axes[i].set_yticks([])
            continue
        
        if metrica == '# Trades':
            df_metrica_plot[metrica] = pd.to_numeric(df_metrica_plot[metrica], errors='coerce').fillna(0).astype(int)
        else:
            df_metrica_plot[metrica] = pd.to_numeric(df_metrica_plot[metrica], errors='coerce').fillna(0)

        # Ordenar por métrica atual (decrescente, exceto Max. Drawdown que é melhor menor)
        if metrica == 'Max. Drawdown [%]':
            df_metrica_plot = df_metrica_plot.sort_values(by=metrica, ascending=True)
        else:
            df_metrica_plot = df_metrica_plot.sort_values(by=metrica, ascending=False)


        bars = df_metrica_plot[metrica].plot(kind='bar', ax=axes[i], colormap='viridis', width=0.8)
        axes[i].set_title(metrica, fontsize=14)
        axes[i].set_ylabel(metrica, fontsize=10)
        axes[i].set_xlabel('Ativo' if i == num_metricas - 1 else '', fontsize=10)
        axes[i].set_xticklabels(axes[i].get_xticklabels(), rotation=45, ha="right", fontsize=9) # Fonte menor para labels X
        axes[i].grid(axis='y', linestyle='--')

        # --- INÍCIO: Adicionar valores nas barras ---
        for p in bars.patches:
            width = p.get_width()
            height = p.get_height()
            x, y = p.get_xy()
            
            # Formatação do texto
            text_value = ""
            if metrica == '# Trades':
                text_value = f"{int(height)}"
            elif metrica == 'Max. Drawdown [%]': # Max Drawdown é negativo
                 text_value = f"{height:.2f}%"
            else: # Win Rate e outros percentuais
                text_value = f"{height:.2f}%"

            if not (isinstance(height, (int, float)) and height == 0 and pd.isna(height)): # Evitar plotar para NaN convertido para 0 se não for #Trades
                 if height == 0 and metrica != '# Trades' and df_metrica_plot.loc[df_metrica_plot.index[bars.patches.index(p)], metrica] == 0 and pd.isna(df_plot_original.set_index('Asset').loc[df_metrica_plot.index[bars.patches.index(p)], metrica]):
                     pass # Não plota o 0.00% se o original era NaN e a métrica não é # Trades
                 else:
                    axes[i].text(x + width/2,
                                y + height + (0.01 * abs(height) if height >= 0 else -0.03 * abs(height) - 0.01*abs(axes[i].get_ylim()[1] - axes[i].get_ylim()[0])), # Ajuste de posição
                                text_value,
                                ha='center',
                                va='bottom' if height >= 0 else 'top',
                                fontsize=8, # Tamanho da fonte dos valores
                                color='black')
        # --- FIM: Adicionar valores nas barras ---

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()


def gerar_visualizacoes(df_resultados):
    """
    Função principal para gerar todas as visualizações dos resultados do backtest.
    """
    print("\nGerando visualizações dos resultados do backtest...")
    if df_resultados is None or df_resultados.empty:
        print("DataFrame de resultados não fornecido ou vazio. Nenhuma visualização será gerada.")
        return

    # Garante que as colunas numéricas estão no tipo correto
    cols_numericas_para_converter = ['Return [%]', 'Buy & Hold Return [%]', 'Win Rate [%]', 
                                     '# Trades', 'Profit Factor', 'Max. Drawdown [%]', 'Avg. Trade [%]',
                                     'Sharpe Ratio', 'Sortino Ratio']
    for col in cols_numericas_para_converter:
        if col in df_resultados.columns:
            df_resultados[col] = pd.to_numeric(df_resultados[col], errors='coerce')
        else:
            print(f"Aviso: Coluna '{col}' esperada para conversão numérica não foi encontrada no DataFrame.")


    # Chama as funções de plotagem
    plotar_retorno_comparativo(df_resultados.copy()) # Passa uma cópia para evitar SettingWithCopyWarning
    plotar_metricas_chave(df_resultados.copy())
    # Adicionar chamadas para outras funções de plotagem aqui (ex: tabela)

    print("Visualizações geradas.")

# Exemplo de como o backtester.py poderia chamar (APENAS PARA TESTE DENTRO DESTE ARQUIVO)
# if __name__ == '__main__':
#     # Criar um DataFrame de exemplo para testar as funções de plotagem
#     dados_exemplo = {
#         'Asset': ['SOLUSDT', 'SUIUSDT', 'LTCUSDT', 'ETHUSDT', 'DOTUSDT', 'LINKUSDT', 'ADAUSDT', 'XRPUSDT', 'AVAXUSDT', 'DOGEUSDT', 'SHIB1000USDT', 'BNBUSDT', 'TRXUSDT'],
#         'Return [%]': [11.03, 8.93, 8.67, 6.88, 5.42, 4.12, 4.12, 4.03, 3.12, 2.40, 1.42, 0.33, -1.69],
#         'Buy & Hold Return [%]': [1.56, -3.40, 7.55, 2.08, -4.22, -4.27, -1.66, -0.05, -8.96, -2.46, -6.63, 0.63, -2.42],
#         'Win Rate [%]': [55.56, 42.86, 50.00, 50.00, 40.00, 41.67, 41.67, 37.50, 36.36, 40.00, 33.33, 0.00, 0.00],
#         '# Trades': [9, 21, 10, 8, 10, 12, 12, 8, 11, 10, 12, 1, 1],
#         'Profit Factor': [2.50, 1.50, 2.00, 2.00, 1.33, 1.43, 1.43, 1.20, 1.14, 1.33, 1.00, 0.00, 0.00],
#         'Max. Drawdown [%]': [-5.83, -14.93, -5.99, -5.41, -9.69, -13.71, -9.65, -6.33, -11.95, -8.50, -10.48, -4.95, -3.23],
#         'Avg. Trade [%]': [1.29, 0.53, 0.96, 0.96, 0.36, 0.46, 0.46, 0.21, 0.14, 0.36, -0.04, -2.00, -2.00],
#         'Avg. Trade Duration': ['1 days 00:23:00', '0 days 07:47:00', '0 days 20:01:00', '1 days 02:45:00', '0 days 18:57:00', '0 days 16:27:00', '0 days 17:23:00', '0 days 22:37:00', '0 days 10:41:00', '0 days 20:54:00', '0 days 16:00:00', '7 days 05:54:00', '0 days 15:06:00'],
#         'Sharpe Ratio': [1.79, 1.04, 1.67, 2.94, 1.91, 1.34, 1.13, 2.40, 1.32, 0.84, 1.24, -0.35, 0.61],
#         'Sortino Ratio': [198.79, 30.85, 79.45, 104.23, 39.97, 8.44, 8.09, 40.94, 18.95, 2.55, 10.01, -0.44, 1.07],
#         'Start': ['2025-04-27 02:51:00'] * 13, # Simplificado
#         'End': ['2025-05-07 01:18:00'] * 13,   # Simplificado
#         'Duration': ['9 days 22:27:00'] * 13 # Simplificado
#     }
#     df_exemplo = pd.DataFrame(dados_exemplo)

    # Converter 'Avg. Trade Duration' e 'Duration' para timedelta se for usar em plots
    # df_exemplo['Avg. Trade Duration'] = pd.to_timedelta(df_exemplo['Avg. Trade Duration'], errors='coerce')
    # df_exemplo['Duration'] = pd.to_timedelta(df_exemplo['Duration'], errors='coerce')

#     gerar_visualizacoes(df_exemplo)