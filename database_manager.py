# database_manager.py
import sqlite3
from datetime import datetime
import json
import pandas as pd
import os # <--- IMPORTAR O MÓDULO OS

# Define o diretório onde este script (database_manager.py) está localizado.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Constrói o caminho para o arquivo de banco de dados DENTRO da subpasta 'dashboard_backtest'.
# Isso assume que 'dashboard_backtest' é uma subpasta direta do diretório
# que contém database_manager.py.
DATABASE_NAME = os.path.join(_SCRIPT_DIR, 'dashboard_backtest', 'backtest_results.db')

# print(f"DATABASE_MANAGER: Usando banco de dados em: {DATABASE_NAME}") # Para depuração

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados SQLite."""
    # Garante que o diretório do banco de dados exista, se não existir, cria.
    db_dir = os.path.dirname(DATABASE_NAME)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir) # Cria o diretório se ele não existir
        print(f"DATABASE_MANAGER: Criado diretório do banco de dados: {db_dir}")

    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row # Permite acessar colunas por nome
    return conn

def create_tables():
    """Cria as tabelas 'Execucoes' e 'Resultados_Ativos' se não existirem."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Execucoes (
            id_execucao INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_execucao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            timeframe TEXT,
            dias_historico INTEGER,
            lista_ativos TEXT,
            fast_ma_type TEXT,
            fast_ma_length INTEGER,
            slow_ma_type TEXT,
            slow_ma_length INTEGER,
            zonas_periodo INTEGER,
            vader_params TEXT,
            sl_percent REAL,
            tp_rr REAL,
            equity_fraction_per_trade REAL,
            initial_cash REAL,
            commission_rate REAL,
            margin REAL,
            descricao TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Resultados_Ativos (
            id_resultado INTEGER PRIMARY KEY AUTOINCREMENT,
            id_execucao INTEGER,
            Asset TEXT,
            StartTime TIMESTAMP,
            EndTime TIMESTAMP,
            Duration TEXT,
            Exposure_Time_Percent REAL,
            Equity_Final REAL,
            Equity_Peak REAL,
            Return_Percent REAL,
            Buy_Hold_Return_Percent REAL,
            Return_Ann_Percent REAL,
            Volatility_Ann_Percent REAL,
            Sharpe_Ratio REAL,
            Sortino_Ratio REAL,
            Calmar_Ratio REAL,
            Max_Drawdown_Percent REAL,
            Avg_Drawdown_Percent REAL,
            Max_Drawdown_Duration TEXT,
            Avg_Drawdown_Duration TEXT,
            Num_Trades INTEGER,
            Win_Rate_Percent REAL,
            Best_Trade_Percent REAL,
            Worst_Trade_Percent REAL,
            Avg_Trade_Percent REAL,
            Max_Trade_Duration TEXT,
            Avg_Trade_Duration TEXT,
            Profit_Factor REAL,
            Expectancy_Percent REAL,
            SQN REAL,
            _strategy TEXT,
            Foi_Otimizado BOOLEAN DEFAULT FALSE, 
            Estrategia_Descricao TEXT,              
            FOREIGN KEY (id_execucao) REFERENCES Execucoes (id_execucao)
        )
    ''')
    conn.commit()
    conn.close()
    print(f"Banco de dados '{DATABASE_NAME}' e tabelas verificados/criados.")

# ... (resto do arquivo database_manager.py como estava antes,
# incluindo registrar_execucao e registrar_resultados_ativos,
# e o bloco if __name__ == '__main__':) ...

def registrar_execucao(params_execucao):
    """
    Registra uma nova execução na tabela 'Execucoes'.
    Args:
        params_execucao (dict): Dicionário contendo os parâmetros da execução.
                                  As chaves devem corresponder aos nomes das colunas.
    Returns:
        int: O ID da execução registrada.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Converte listas/dicionários para JSON string onde aplicável
    if 'lista_ativos' in params_execucao and isinstance(params_execucao['lista_ativos'], list):
        params_execucao['lista_ativos'] = json.dumps(params_execucao['lista_ativos'])
    if 'vader_params' in params_execucao and isinstance(params_execucao['vader_params'], dict):
        params_execucao['vader_params'] = json.dumps(params_execucao['vader_params'])

    # Garante que todas as chaves do dicionário correspondem a colunas existentes
    # Obtém as colunas da tabela Execucoes
    cursor.execute("PRAGMA table_info(Execucoes)")
    colunas_tabela_execucoes = [info[1] for info in cursor.fetchall()]
    
    # Filtra params_execucao para incluir apenas chaves que são colunas na tabela
    params_filtrados = {k: v for k, v in params_execucao.items() if k in colunas_tabela_execucoes}


    if not params_filtrados:
        conn.close()
        raise ValueError("Nenhum parâmetro fornecido corresponde às colunas da tabela Execucoes.")

    cols = ', '.join(params_filtrados.keys())
    placeholders = ', '.join(['?'] * len(params_filtrados))
    sql = f"INSERT INTO Execucoes ({cols}) VALUES ({placeholders})"
    
    try:
        cursor.execute(sql, tuple(params_filtrados.values()))
        id_exec = cursor.lastrowid
        conn.commit()
    except sqlite3.Error as e:
        print(f"Erro ao registrar execução no banco de dados: {e}")
        print(f"SQL: {sql}")
        print(f"Valores: {tuple(params_filtrados.values())}")
        id_exec = None # Ou levanta o erro novamente
    finally:
        conn.close()
        
    return id_exec

def registrar_resultados_ativos(id_execucao, lista_stats_ativos):
    """
    Registra os resultados de múltiplos ativos para uma dada execução.
    """
    if not lista_stats_ativos:
        print("DEBUG: lista_stats_ativos está vazia. Nada para registrar.")
        return

    print(f"DEBUG: Iniciando registrar_resultados_ativos para id_execucao: {id_execucao}")
    print(f"DEBUG: Número de ativos recebidos: {len(lista_stats_ativos)}")
    if lista_stats_ativos:
        # Só imprime o início do dicionário para evitar o log gigante do _equity_curve e _trades
        print(f"DEBUG: Exemplo do primeiro item em lista_stats_ativos (chaves e alguns valores):")
        for k, v in lista_stats_ativos[0].items():
            if k not in ['_equity_curve', '_trades']:
                print(f"  {k}: {str(v)[:100]}") # Imprime apenas os primeiros 100 caracteres do valor
            else:
                print(f"  {k}: <DataFrame ou Objeto Complexo>")


    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(Resultados_Ativos)")
    colunas_tabela_resultados = [info[1] for info in cursor.fetchall()]
    print(f"DEBUG: Colunas da tabela Resultados_Ativos: {colunas_tabela_resultados}")

    registros_para_inserir = []
    for idx, stats_original in enumerate(lista_stats_ativos):
        stats = stats_original.copy()
        # print(f"\nDEBUG: Processando ativo #{idx+1}, dados originais: {stats}") # Removido ou reduzido para evitar log excessivo
        registro = {'id_execucao': id_execucao}

        mapeamento_chaves = {
            'Start': 'StartTime',
            'End': 'EndTime',
            'Duration': 'Duration',
            'Exposure Time [%]': 'Exposure_Time_Percent',
            'Equity Final [$]': 'Equity_Final',
            'Equity Peak [$]': 'Equity_Peak',
            'Return [%]': 'Return_Percent',
            'Buy & Hold Return [%]': 'Buy_Hold_Return_Percent',
            'Return (Ann.) [%]': 'Return_Ann_Percent',
            'Volatility (Ann.) [%]': 'Volatility_Ann_Percent',
            'Sharpe Ratio': 'Sharpe_Ratio',
            'Sortino Ratio': 'Sortino_Ratio',
            'Calmar Ratio': 'Calmar_Ratio',
            'Max. Drawdown [%]': 'Max_Drawdown_Percent',
            'Avg. Drawdown [%]': 'Avg_Drawdown_Percent',
            'Max. Drawdown Duration': 'Max_Drawdown_Duration',
            'Avg. Drawdown Duration': 'Avg_Drawdown_Duration',
            '# Trades': 'Num_Trades',
            'Win Rate [%]': 'Win_Rate_Percent',
            'Best Trade [%]': 'Best_Trade_Percent',
            'Worst Trade [%]': 'Worst_Trade_Percent',
            'Avg. Trade [%]': 'Avg_Trade_Percent',
            'Max. Trade Duration': 'Max_Trade_Duration',
            'Avg. Trade Duration': 'Avg_Trade_Duration',
            'Profit Factor': 'Profit_Factor',
            'Expectancy [%]': 'Expectancy_Percent',
            'SQN': 'SQN',
            'Asset': 'Asset', # Já deve estar correto
            '_strategy': '_strategy',
            'Foi_Otimizado': 'Foi_Otimizado',           # Chave do backtester.py
            'Estrategia_Descricao': 'Estrategia_Descricao', # Chave do backtester.py
            'EquityCurve_JSON': 'EquityCurve_JSON',
            'Trades_JSON': 'Trades_JSON'                # Chave do dicionário de stats -> Nome da coluna no DB
            # --- FIM DA MODIFICAÇÃO ---
            # Adicione outras chaves que vêm da biblioteca backtesting.py se necessário
        }
        
        # Chaves que são DataFrames ou outros objetos complexos e não devem ser inseridas diretamente
        chaves_para_ignorar = ['_equity_curve', '_trades', 'Commissions [$]', 'Alpha [%]', 'Beta', 'Kelly Criterion']


        keys_mapeadas_para_este_ativo = 0
        for key_original, value in stats.items():
            if key_original in chaves_para_ignorar:
                continue

            db_key = mapeamento_chaves.get(key_original, key_original) # Usa a chave original se não mapeada

            if db_key in colunas_tabela_resultados: # Verifica se a chave (mapeada ou original) é uma coluna
                keys_mapeadas_para_este_ativo += 1
                if db_key == '_strategy': # Tratamento específico para _strategy
                    if hasattr(value, '__name__'):
                        registro[db_key] = value.__name__ # Salva o nome da classe
                    else:
                        registro[db_key] = str(value) # Fallback para string
                elif db_key in ['StartTime', 'EndTime']:
                    if pd.isna(value) or value is None: registro[db_key] = None
                    elif isinstance(value, str):
                        try: pd.to_datetime(value); registro[db_key] = value
                        except ValueError: registro[db_key] = str(value)
                    else: registro[db_key] = value.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(value) else None
                elif db_key in ['Duration', 'Max_Drawdown_Duration', 'Avg_Drawdown_Duration', 'Max_Trade_Duration', 'Avg_Trade_Duration']:
                    registro[db_key] = str(value) if not pd.isna(value) else None # Garante que Timedelta seja string
                elif pd.isna(value):
                    registro[db_key] = None
                else:
                    registro[db_key] = value
            # else:
            #     print(f"DEBUG: Chave '{key_original}' (mapeada para '{db_key}') não é uma coluna na tabela Resultados_Ativos.")


        print(f"DEBUG: Ativo #{idx+1} ({stats.get('Asset', 'N/A')}), chaves mapeadas/diretas para DB: {keys_mapeadas_para_este_ativo}")
        registro_final = {k: v for k, v in registro.items() if k in colunas_tabela_resultados}
        print(f"DEBUG: Ativo #{idx+1}, registro_final antes de adicionar: { {k: v for k, v in registro_final.items() if k != '_equity_curve' and k != '_trades'} }") # Evita imprimir DataFrames grandes

        if 'Asset' in registro_final and 'id_execucao' in registro_final:
            registros_para_inserir.append(registro_final)
        else:
            print(f"DEBUG: Ativo #{idx+1} DESCARTADO. Faltando Asset ou id_execucao no registro_final.")

    print(f"DEBUG: Total de registros_para_inserir: {len(registros_para_inserir)}")
    if registros_para_inserir:
        # Pega as colunas do primeiro registro para construir o SQL dinamicamente
        primeiro_registro_chaves_validas = list(registros_para_inserir[0].keys())
        
        cols = ', '.join(f'"{k}"' for k in primeiro_registro_chaves_validas) # Colocar nomes de coluna entre aspas
        placeholders = ', '.join(['?'] * len(primeiro_registro_chaves_validas))
        sql = f"INSERT INTO Resultados_Ativos ({cols}) VALUES ({placeholders})"
        print(f"DEBUG SQL INSERT: {sql}")
        
        lista_valores_tuplas = []
        for reg_idx, reg in enumerate(registros_para_inserir):
            valores_tupla = [reg.get(chave_mestra) for chave_mestra in primeiro_registro_chaves_validas]
            lista_valores_tuplas.append(tuple(valores_tupla))
            if reg_idx < 1: # DEBUG: Imprime apenas o primeiro conjunto de valores
                # Evita imprimir DataFrames na tupla de valores
                valores_tupla_debug = [str(v)[:50] + '...' if isinstance(v, (pd.DataFrame, pd.Series)) else v for v in valores_tupla]
                print(f"DEBUG Valores Tupla #{reg_idx+1} (para SQL): {tuple(valores_tupla_debug)}")

        if lista_valores_tuplas:
            try:
                cursor.executemany(sql, lista_valores_tuplas)
                conn.commit()
                print(f"DEBUG: {len(lista_valores_tuplas)} registros inseridos em Resultados_Ativos.")
            except sqlite3.Error as e:
                print(f"ERRO AO INSERIR no banco de dados: {e}")
                print(f"SQL: {sql}")
                if lista_valores_tuplas:
                     print(f"Primeiro conjunto de valores problemático: {lista_valores_tuplas[0]}") # Imprime a tupla exata
            finally:
                conn.close()
        else:
            print("DEBUG: lista_valores_tuplas estava vazia. Nada foi inserido.")
            conn.close()
    else:
        print("DEBUG: registros_para_inserir estava vazio. Nenhuma inserção tentada.")
        conn.close()

if __name__ == '__main__':
    create_tables()
    print("Execução de database_manager.py concluída. Banco de dados e tabelas devem estar prontos.")
    # Você pode adicionar aqui chamadas de teste para registrar_execucao e registrar_resultados_ativos
    # se quiser testar a inserção de dados diretamente.
    # Exemplo:
    # params_teste = {
    #     'timeframe': '3', 'dias_historico': 10, 
    #     'lista_ativos': json.dumps(["ETHUSDT", "SOLUSDT"]), # Precisa ser JSON string
    #     'fast_ma_type': 'EMA', 'fast_ma_length': 12,
    #     'slow_ma_type': 'EMA', 'slow_ma_length': 26,
    #     'zonas_periodo': 1500, 
    #     'vader_params': json.dumps({'length': 10, 'der_avg': 5}), # Precisa ser JSON string
    #     'sl_percent': 0.02, 'tp_rr': 2.0, 'equity_fraction_per_trade': 0.1,
    #     'initial_cash': 50000.0, 'commission_rate': 0.0006, 'margin': 0.1,
    #     'descricao': 'Teste de inserção via main do database_manager'
    # }
    # exec_id = registrar_execucao(params_teste)
    # if exec_id:
    #     print(f"Execução de teste registrada com ID: {exec_id}")
    #     resultados_teste = [
    #         {'Asset': 'ETHUSDT', 'Return [%]': 11.37, '# Trades': 6, 'Win Rate [%]': 66.67, 'Max. Drawdown [%]': -4.58, 'Profit Factor': 4.0, 'Sharpe Ratio': 2.97, 'Sortino Ratio': 464.16, 'Start': datetime(2025,4,27,3,36,0), 'End': datetime(2025,5,7,2,3,0), 'Duration': "9 days"},
    #         {'Asset': 'SOLUSDT', 'Return [%]': 4.60, '# Trades': 9, 'Win Rate [%]': 44.44, 'Max. Drawdown [%]': -5.83, 'Profit Factor': 1.6, 'Sharpe Ratio': 3.05, 'Sortino Ratio': 28.47, 'Start': datetime(2025,4,27,3,36,0), 'End': datetime(2025,5,7,2,3,0), 'Duration': "9 days"}
    #     ]
    #     registrar_resultados_ativos(exec_id, resultados_teste)
    #     print(f"Resultados de teste registrados para execução ID: {exec_id}")