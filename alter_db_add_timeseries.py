# alter_db_add_timeseries.py
import sqlite3
import os

# Pega o diretório do script atual
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Assume que o dashboard_backtest é uma subpasta e o DB está lá
DATABASE_NAME = os.path.join(_SCRIPT_DIR, 'dashboard_backtest', 'backtest_results.db')
# Ou se você já ajustou DATABASE_NAME em database_manager.py para apontar corretamente:
# from database_manager import DATABASE_NAME # Se preferir

conn = sqlite3.connect(DATABASE_NAME)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE Resultados_Ativos ADD COLUMN EquityCurve_JSON TEXT")
    print("Coluna EquityCurve_JSON adicionada a Resultados_Ativos.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("Coluna EquityCurve_JSON já existe em Resultados_Ativos.")
    else:
        print(f"Erro ao adicionar EquityCurve_JSON: {e}")
        # raise # Descomente se quiser que o script pare em caso de outros erros

try:
    cursor.execute("ALTER TABLE Resultados_Ativos ADD COLUMN Trades_JSON TEXT")
    print("Coluna Trades_JSON adicionada a Resultados_Ativos.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("Coluna Trades_JSON já existe em Resultados_Ativos.")
    else:
        print(f"Erro ao adicionar Trades_JSON: {e}")
        # raise

conn.commit()
conn.close()
print("Verificação/adição de colunas para séries temporais concluída.")