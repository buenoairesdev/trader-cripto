# dashboard_backtest/db_queries.py
import sqlite3
import pandas as pd
import json
import os

# Define o diretório onde este script (db_queries.py) está localizado.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# O banco de dados está na mesma pasta que este script.
DATABASE_NAME = os.path.join(_SCRIPT_DIR, 'backtest_results.db')

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados SQLite."""
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        conn.row_factory = sqlite3.Row # Permite acessar colunas por nome
        return conn
    except sqlite3.Error as e:
        print(f"Erro ao conectar ao banco de dados SQLite: {e}")
        raise # Re-levanta a exceção para que o chamador saiba que a conexão falhou

def get_all_executions():
    """Busca todas as execuções da tabela Execucoes para exibição inicial."""
    try:
        conn = get_db_connection()
        # Seleciona colunas relevantes para a visão geral
        query = "SELECT id_execucao, timestamp_execucao, timeframe, dias_historico, descricao FROM Execucoes ORDER BY timestamp_execucao DESC"
        df_execucoes = pd.read_sql_query(query, conn)
        conn.close()
        return df_execucoes
    except Exception as e:
        print(f"Erro ao buscar todas as execuções: {e}")
        return pd.DataFrame() # Retorna DataFrame vazio em caso de erro

def get_execution_details(execution_id: int):
    """Busca os detalhes completos (todos os parâmetros) de uma execução específica."""
    if not isinstance(execution_id, (int, float)): # Permite float se vier de JS como número
        try:
            execution_id = int(execution_id)
        except (ValueError, TypeError):
            print(f"Erro: ID da execução inválido (tipo): {execution_id}")
            return pd.Series(dtype=object)

    try:
        conn = get_db_connection()
        query = "SELECT * FROM Execucoes WHERE id_execucao = ?"
        df_execucao = pd.read_sql_query(query, conn, params=(execution_id,))
        conn.close()

        if df_execucao.empty:
            print(f"Nenhuma execução encontrada com ID: {execution_id}")
            return pd.Series(dtype=object)

        dados_execucao = df_execucao.iloc[0].copy() # Usa .copy() para evitar SettingWithCopyWarning

        # Tenta decodificar campos JSON (lista_ativos, vader_params)
        for col in ['lista_ativos', 'vader_params']:
            if col in dados_execucao and isinstance(dados_execucao[col], str):
                try:
                    dados_execucao.loc[col] = json.loads(dados_execucao[col])
                except json.JSONDecodeError:
                    print(f"Aviso em get_execution_details: Não foi possível decodificar '{col}' para a execução {execution_id}.")
        return dados_execucao
    except Exception as e:
        print(f"Erro ao buscar detalhes da execução {execution_id}: {e}")
        return pd.Series(dtype=object)

def get_asset_results_for_execution(execution_id: int):
    """
    Busca os resultados de TODOS os ativos para uma execução específica.
    Também realiza a conversão de tipos para colunas numéricas e booleanas.
    """
    if not isinstance(execution_id, (int, float)):
        try:
            execution_id = int(execution_id)
        except (ValueError, TypeError):
            print(f"Erro: ID da execução inválido para resultados de ativos (tipo): {execution_id}")
            return pd.DataFrame()

    try:
        conn = get_db_connection()
        query = "SELECT * FROM Resultados_Ativos WHERE id_execucao = ? ORDER BY Asset"
        df_resultados = pd.read_sql_query(query, conn, params=(execution_id,))
        conn.close()

        if df_resultados.empty:
            # print(f"Nenhum resultado de ativo encontrado para a execução ID: {execution_id}")
            return pd.DataFrame()

        # Conversões de tipo
        cols_numericas_float = [
            'Exposure_Time_Percent', 'Equity_Final', 'Equity_Peak', 'Return_Percent',
            'Buy_Hold_Return_Percent', 'Return_Ann_Percent', 'Volatility_Ann_Percent',
            'Sharpe_Ratio', 'Sortino_Ratio', 'Calmar_Ratio', 'Max_Drawdown_Percent',
            'Avg_Drawdown_Percent', 'Win_Rate_Percent', 'Best_Trade_Percent',
            'Worst_Trade_Percent', 'Avg_Trade_Percent', 'Profit_Factor',
            'Expectancy_Percent', 'SQN'
        ]
        for col in cols_numericas_float:
            if col in df_resultados.columns:
                df_resultados[col] = pd.to_numeric(df_resultados[col], errors='coerce')

        if 'Num_Trades' in df_resultados.columns:
            df_resultados['Num_Trades'] = pd.to_numeric(df_resultados['Num_Trades'], errors='coerce').fillna(0).astype(int)

        for col_tempo in ['StartTime', 'EndTime']:
            if col_tempo in df_resultados.columns:
                df_resultados[col_tempo] = pd.to_datetime(df_resultados[col_tempo], errors='coerce')
        
        if 'Foi_Otimizado' in df_resultados.columns:
            # Mapeia explicitamente para evitar problemas com tipos mistos ou strings inesperadas
            # SQLite guarda booleanos como 0 ou 1
            df_resultados['Foi_Otimizado'] = df_resultados['Foi_Otimizado'].apply(lambda x: True if str(x).lower() in ['1', 'true', 'yes'] else False if str(x).lower() in ['0', 'false', 'no'] else None)
            df_resultados['Foi_Otimizado'] = df_resultados['Foi_Otimizado'].astype('boolean') # Usa o tipo booleano do Pandas que suporta NA


        # As colunas de duração (Duration, Max_Drawdown_Duration, etc.) são mantidas como string
        # pois podem conter formatos como "X days HH:MM:SS" que o pd.to_timedelta pode não gostar universalmente
        # ou podem já estar como strings de Timedelta. Se precisar de cálculos, converter no momento do uso.

        return df_resultados
    except Exception as e:
        print(f"Erro ao buscar resultados dos ativos para execução {execution_id}: {e}")
        return pd.DataFrame()