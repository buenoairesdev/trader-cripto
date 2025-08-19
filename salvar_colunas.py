# Script rápido para adicionar colunas (execute uma vez)
import sqlite3
conn = sqlite3.connect('backtest_results.db')
cursor = conn.cursor()
try:
    cursor.execute("ALTER TABLE Resultados_Ativos ADD COLUMN Foi_Otimizado BOOLEAN DEFAULT FALSE")
    print("Coluna Foi_Otimizado adicionada.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("Coluna Foi_Otimizado já existe.")
    else: raise
try:
    cursor.execute("ALTER TABLE Resultados_Ativos ADD COLUMN Estrategia_Descricao TEXT")
    print("Coluna Estrategia_Descricao adicionada.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("Coluna Estrategia_Descricao já existe.")
    else: raise
conn.commit()
conn.close()