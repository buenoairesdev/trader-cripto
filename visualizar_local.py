# visualizar_local.py
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots # Importação para subplots
from plotly.offline import plot as plotly_offline_plot
import json
import re

DATABASE_NAME = 'backtest_results.db'

def sanitizar_nome_arquivo(nome: str) -> str:
    """
    Remove ou substitui caracteres inválidos para nomes de arquivo.
    """
    nome_sanitizado = re.sub(r'[\\/*?:"<>|]', "", nome)
    nome_sanitizado = re.sub(r'[\s,.:()]+', "_", nome_sanitizado)
    nome_sanitizado = re.sub(r'_+', "_", nome_sanitizado)
    nome_sanitizado = nome_sanitizado.strip('_')
    return nome_sanitizado[:150]

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def listar_execucoes_disponiveis():
    """
    Busca e exibe as execuções disponíveis na tabela Execucoes.
    """
    print("\nBuscando execuções disponíveis...")
    try:
        conn = get_db_connection()
        query = "SELECT id_execucao, timestamp_execucao, timeframe, dias_historico, descricao FROM Execucoes ORDER BY timestamp_execucao DESC"
        df_execucoes = pd.read_sql_query(query, conn)
        conn.close()

        if df_execucoes.empty:
            print("Nenhuma execução encontrada no banco de dados.")
            return pd.DataFrame()

        print("\nExecuções Disponíveis:")
        for index, row in df_execucoes.iterrows():
            print(f"  ID: {row['id_execucao']}, Data: {row['timestamp_execucao']}, "
                  f"Timeframe: {row['timeframe']}, Dias: {row['dias_historico']}, Descrição: {row['descricao']}")
        return df_execucoes

    except sqlite3.Error as e:
        print(f"Erro ao buscar execuções: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Erro inesperado ao listar execuções: {e}")
        return pd.DataFrame()

def buscar_dados_execucao_completa(id_execucao_selecionada: int):
    """
    Busca os detalhes de uma execução específica e os resultados dos ativos associados.
    """
    print(f"\nBuscando dados para a execução ID: {id_execucao_selecionada}...")
    try:
        conn = get_db_connection()
        query_execucao = "SELECT * FROM Execucoes WHERE id_execucao = ?"
        cursor = conn.cursor()
        cursor.execute(query_execucao, (id_execucao_selecionada,))
        execucao_data_raw = cursor.fetchone()

        if not execucao_data_raw:
            print(f"Nenhuma execução encontrada com o ID: {id_execucao_selecionada}")
            conn.close()
            return None, None
        
        dados_execucao = pd.Series(dict(execucao_data_raw))

        if 'lista_ativos' in dados_execucao and isinstance(dados_execucao['lista_ativos'], str):
            try:
                dados_execucao['lista_ativos'] = json.loads(dados_execucao['lista_ativos'])
            except json.JSONDecodeError:
                print(f"Aviso: Não foi possível decodificar 'lista_ativos' para a execução {id_execucao_selecionada}.")
        
        if 'vader_params' in dados_execucao and isinstance(dados_execucao['vader_params'], str):
            try:
                dados_execucao['vader_params'] = json.loads(dados_execucao['vader_params'])
            except json.JSONDecodeError:
                print(f"Aviso: Não foi possível decodificar 'vader_params' para a execução {id_execucao_selecionada}.")

        query_resultados = "SELECT * FROM Resultados_Ativos WHERE id_execucao = ?"
        df_resultados_ativos = pd.read_sql_query(query_resultados, conn, params=(id_execucao_selecionada,))
        
        for col_tempo in ['StartTime', 'EndTime']:
            if col_tempo in df_resultados_ativos.columns:
                df_resultados_ativos[col_tempo] = pd.to_datetime(df_resultados_ativos[col_tempo], errors='coerce')
        
        cols_numericas_para_converter = [
            'Exposure_Time_Percent', 'Equity_Final', 'Equity_Peak', 'Return_Percent',
            'Buy_Hold_Return_Percent', 'Return_Ann_Percent', 'Volatility_Ann_Percent',
            'Sharpe_Ratio', 'Sortino_Ratio', 'Calmar_Ratio', 'Max_Drawdown_Percent',
            'Avg_Drawdown_Percent', 'Win_Rate_Percent', 'Best_Trade_Percent',
            'Worst_Trade_Percent', 'Avg_Trade_Percent', 'Profit_Factor',
            'Expectancy_Percent', 'SQN', 'Num_Trades'
        ]
        for col in cols_numericas_para_converter:
            if col in df_resultados_ativos.columns:
                df_resultados_ativos[col] = pd.to_numeric(df_resultados_ativos[col], errors='coerce')

        if df_resultados_ativos.empty:
            print(f"Nenhum resultado de ativo encontrado para a execução ID: {id_execucao_selecionada}")
        
        conn.close()
        return dados_execucao, df_resultados_ativos

    except sqlite3.Error as e:
        print(f"Erro ao buscar dados da execução completa: {e}")
        return None, None
    except Exception as e:
        print(f"Erro inesperado ao buscar dados da execução: {e}")
        return None, None

def plotar_todos_graficos_em_subplots(df_resultados_ativos: pd.DataFrame, titulo_execucao: str):
    """
    Gera UM arquivo HTML com TODOS os gráficos de análise (Retorno Comparativo e Métricas Chave)
    usando subplots do Plotly, empilhados verticalmente, com melhor aproveitamento de espaço.
    """
    if df_resultados_ativos is None or df_resultados_ativos.empty:
        print("DataFrame de resultados vazio. Não é possível gerar gráficos.")
        return

    metricas_config = {
        'Retorno_Comparativo': {'nome': 'Retorno Estratégia vs Buy & Hold', 'tipo': 'retorno_comparativo'},
        'Sharpe_Ratio': {'nome': 'Sharpe Ratio', 'tipo': 'metrica_individual', 'ordenacao_ascendente': False},
        'Max_Drawdown_Percent': {'nome': 'Max Drawdown (%)', 'tipo': 'metrica_individual', 'ordenacao_ascendente': True},
        'Num_Trades': {'nome': 'Número de Trades', 'tipo': 'metrica_individual', 'ordenacao_ascendente': False},
        'Win_Rate_Percent': {'nome': 'Win Rate (%)', 'tipo': 'metrica_individual', 'ordenacao_ascendente': False},
        'Profit_Factor': {'nome': 'Profit Factor', 'tipo': 'metrica_individual', 'ordenacao_ascendente': False}
    }

    num_total_graficos = len(metricas_config)
    if num_total_graficos == 0:
        print("Nenhuma métrica configurada para plotagem.")
        return

    rows = num_total_graficos
    cols = 1

    subplot_titles = [config['nome'] for config in metricas_config.values()]
    
    # Não vamos usar row_heights por enquanto, para que o Plotly divida a altura igualmente.
    # Se precisar de alturas desiguais, podemos reintroduzir row_heights.
    
    fig = make_subplots(
        rows=rows, cols=cols,
        subplot_titles=subplot_titles,
        vertical_spacing=0.06, # Reduzir um pouco se os gráficos ficarem muito altos
    )

    current_row = 1

    for key_metrica_ou_grafico, config in metricas_config.items():
        nome_grafico = config['nome']
        tipo_grafico = config['tipo']

        # Lógica de plotagem para 'retorno_comparativo' (INALTERADA, exceto row e col)
        if tipo_grafico == 'retorno_comparativo':
            if 'Return_Percent' not in df_resultados_ativos.columns or 'Buy_Hold_Return_Percent' not in df_resultados_ativos.columns:
                print(f"Aviso: Colunas para '{nome_grafico}' não encontradas. Pulando subplot.")
                fig.add_trace(go.Scatter(x=[0.5], y=[0.5], text=f"Dados de '{nome_grafico}' indisponíveis", mode="text"),
                              row=current_row, col=1)
            else:
                df_sorted_retorno = df_resultados_ativos.sort_values(by='Asset')
                fig.add_trace(go.Bar(
                    x=df_sorted_retorno['Asset'],
                    y=df_sorted_retorno['Return_Percent'],
                    name='Retorno Estratégia (%)',
                    text=df_sorted_retorno['Return_Percent'].apply(lambda x: f'{x:.2f}%' if pd.notna(x) else 'N/A'),
                    textposition='auto',
                    marker_color='indianred'
                ), row=current_row, col=1)

                fig.add_trace(go.Bar(
                    x=df_sorted_retorno['Asset'],
                    y=df_sorted_retorno['Buy_Hold_Return_Percent'],
                    name='Buy & Hold (%)',
                    text=df_sorted_retorno['Buy_Hold_Return_Percent'].apply(lambda x: f'{x:.2f}%' if pd.notna(x) else 'N/A'),
                    textposition='auto',
                    marker_color='lightsalmon'
                ), row=current_row, col=1)
                fig.update_yaxes(title_text="Retorno (%)", row=current_row, col=1)


        # Lógica de plotagem para 'metrica_individual' (INALTERADA, exceto row e col)
        elif tipo_grafico == 'metrica_individual':
            key_coluna_metrica = key_metrica_ou_grafico
            ordenacao_ascendente = config['ordenacao_ascendente']

            if key_coluna_metrica not in df_resultados_ativos.columns:
                print(f"Aviso: Métrica '{nome_grafico}' (coluna '{key_coluna_metrica}') não encontrada. Pulando subplot.")
                fig.add_trace(go.Scatter(x=[0.5], y=[0.5], text=f"Dados de '{nome_grafico}' indisponíveis", mode="text"),
                              row=current_row, col=1)
            else:
                df_plot_metrica = df_resultados_ativos.copy()
                if key_coluna_metrica == 'Max_Drawdown_Percent':
                     df_plot_metrica[key_coluna_metrica] = df_plot_metrica[key_coluna_metrica].fillna(0)
                elif df_plot_metrica[key_coluna_metrica].dtype in ['float', 'int', 'float64', 'int64']:
                     df_plot_metrica[key_coluna_metrica] = df_plot_metrica[key_coluna_metrica].fillna(0 if not ordenacao_ascendente else float('inf'))
                
                df_sorted = df_plot_metrica.sort_values(by=key_coluna_metrica, ascending=ordenacao_ascendente)

                if key_coluna_metrica == 'Num_Trades':
                    text_values = df_sorted[key_coluna_metrica].apply(lambda x: f'{int(x)}' if pd.notna(x) else 'N/A')
                else:
                    text_values = df_sorted[key_coluna_metrica].apply(lambda x: f'{x:.2f}' if pd.notna(x) else 'N/A')

                fig.add_trace(go.Bar(
                    x=df_sorted['Asset'],
                    y=df_sorted[key_coluna_metrica],
                    name=nome_grafico,
                    text=text_values,
                    textposition='auto'
                ), row=current_row, col=1)
                fig.update_yaxes(title_text=nome_grafico, row=current_row, col=1)
        
        if not ( (tipo_grafico == 'retorno_comparativo' and ('Return_Percent' not in df_resultados_ativos.columns or 'Buy_Hold_Return_Percent' not in df_resultados_ativos.columns)) or \
                 (tipo_grafico == 'metrica_individual' and key_metrica_ou_grafico not in df_resultados_ativos.columns) ):
            fig.update_xaxes(title_text="Ativo", row=current_row, col=1, tickangle=-45)
        
        current_row += 1

    # --- AJUSTES NO LAYOUT GERAL ---
    fig.update_layout(
        title_text=f'Análise Detalhada da Execução - {titulo_execucao}',
        height=480 * num_total_graficos,  # Aumentar a altura base por gráfico (ex: 350px)
        # width=None, # OMITIR para tentar usar 100% da largura do navegador
        showlegend=True, 
        legend_title_text='Métricas',
        barmode='group' # Importante para o gráfico de retorno comparativo
    )

    filename_base_sanitizado = sanitizar_nome_arquivo(f"analise_vertical_grande_exec_{titulo_execucao}")
    filename = f"{filename_base_sanitizado}.html"

    try:
        plotly_offline_plot(fig, filename=filename, auto_open=True)
        print(f"Gráfico de Análise Vertical (Subplots) salvo como '{filename}' e aberto no navegador.")
    except Exception as e:
        print(f"Erro ao salvar ou abrir o gráfico de subplots '{filename}': {e}")


def main():
    print("Iniciando a ferramenta de Análise de Resultados de Backtest...")
    df_execucoes_disponiveis = listar_execucoes_disponiveis()

    if df_execucoes_disponiveis.empty:
        print("Nenhuma execução para analisar. Encerrando.")
        return

    while True:
        try:
            id_selecionado_str = input("\nDigite o ID da execução que deseja analisar (ou 'sair' para terminar): ")
            if id_selecionado_str.lower() == 'sair':
                break
            id_selecionado = int(id_selecionado_str)
            if id_selecionado not in df_execucoes_disponiveis['id_execucao'].values:
                print("ID inválido. Por favor, escolha um ID da lista.")
                continue
            
            dados_execucao, df_resultados_ativos = buscar_dados_execucao_completa(id_selecionado)

            if dados_execucao is not None and df_resultados_ativos is not None:
                print("\n--- Detalhes da Execução Selecionada ---")
                for k, v in dados_execucao.items():
                    if k == 'lista_ativos' and isinstance(v, list):
                         print(f"  {k.replace('_', ' ').capitalize()}: {', '.join(v[:5])}{'...' if len(v) > 5 else ''} ({len(v)} ativos)")
                    elif k == 'vader_params' and isinstance(v, dict):
                         print(f"  {k.replace('_', ' ').capitalize()}:")
                         for vk, vv in v.items():
                             print(f"    {vk}: {vv}")
                    else:
                        print(f"  {k.replace('_', ' ').capitalize()}: {v}")
                
                print("\n--- Resultados dos Ativos para esta Execução ---")
                if not df_resultados_ativos.empty:
                    cols_display_console = ['Asset', 'Return_Percent', 'Sharpe_Ratio', 'Max_Drawdown_Percent', 'Num_Trades', 'Win_Rate_Percent']
                    cols_existentes = [col for col in cols_display_console if col in df_resultados_ativos.columns]
                    print(df_resultados_ativos[cols_existentes].to_string(index=False))

                    titulo_grafico = dados_execucao.get('descricao', f"ID {id_selecionado}") + f" (TF {dados_execucao.get('timeframe', 'N_A')}m)"
                    
                    plotar_todos_graficos_em_subplots(df_resultados_ativos, titulo_grafico)

                else:
                    print("Não há resultados de ativos para exibir para esta execução.")
            else:
                print(f"Não foi possível carregar os dados para a execução ID {id_selecionado}.")

        except ValueError:
            print("Entrada inválida. Por favor, digite um número de ID ou 'sair'.")
        except Exception as e:
            print(f"Ocorreu um erro no loop principal: {e}")
            import traceback
            traceback.print_exc()

    print("\nAnálise de Resultados de Backtest concluída.")

if __name__ == "__main__":
    main()