# dashboard_backtest/plots.py
import plotly.graph_objects as go
import pandas as pd
import io # Para usar io.StringIO com pd.read_json

# --- Importações de Format, Scheme e Symbol ---
from dash.dash_table.Format import Format, Scheme, Symbol
import dash 


def create_empty_figure(message="Selecione os dados para visualização"):
    """Cria uma figura Plotly vazia com uma mensagem centralizada."""
    fig = go.Figure()
    fig.update_layout(
        xaxis={'visible': False, 'showgrid': False},
        yaxis={'visible': False, 'showgrid': False},
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font_color='white',
        annotations=[{
            'text': message,
            'xref': 'paper',
            'yref': 'paper',
            'x': 0.5,
            'y': 0.5,
            'showarrow': False,
            'font': {'size': 16, 'color': 'grey'}
        }]
    )
    return fig

def plot_retorno_comparativo(df_resultados_ativos: pd.DataFrame):
    """Gera gráfico de barras comparando Retorno Estratégia vs Buy & Hold."""
    if df_resultados_ativos is None or df_resultados_ativos.empty:
        return create_empty_figure("Dados de retorno indisponíveis para plotagem.")

    required_cols = ['Asset', 'Return_Percent', 'Buy_Hold_Return_Percent']
    if not all(col in df_resultados_ativos.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df_resultados_ativos.columns]
        return create_empty_figure(f"Colunas ausentes para gráfico de retorno: {', '.join(missing)}")

    df_plot = df_resultados_ativos.dropna(subset=required_cols).copy()
    if df_plot.empty:
        return create_empty_figure("Sem dados válidos para gráfico de retorno.")

    df_sorted = df_plot.sort_values(by='Asset')
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_sorted['Asset'],
        y=df_sorted['Return_Percent'],
        name='Retorno Estratégia', 
        text=df_sorted['Return_Percent'].apply(lambda x: f'{x:.2f}%' if pd.notna(x) else 'N/A'),
        textposition='auto',
        marker_color='indianred'
    ))
    fig.add_trace(go.Bar(
        x=df_sorted['Asset'],
        y=df_sorted['Buy_Hold_Return_Percent'],
        name='Buy & Hold', 
        text=df_sorted['Buy_Hold_Return_Percent'].apply(lambda x: f'{x:.2f}%' if pd.notna(x) else 'N/A'),
        textposition='auto',
        marker_color='lightsalmon'
    ))
    fig.update_layout(
        title_text='Retorno Estratégia vs Buy & Hold',
        barmode='group',
        xaxis_tickangle=-45,
        legend_title_text='Comparativo', 
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font_color='white',
        yaxis_gridcolor='rgba(128,128,128,0.3)',
        xaxis_gridcolor='rgba(128,128,128,0.3)',
        margin=dict(l=40, r=20, t=60, b=120) 
    )
    fig.update_yaxes(title_text="Retorno (%)")
    return fig

def plot_generic_metric_bar(df_resultados_ativos: pd.DataFrame, metric_col: str, title: str, higher_is_better: bool = True, y_axis_suffix: str = ""):
    """Gera um gráfico de barras genérico para uma métrica específica."""
    if df_resultados_ativos is None or df_resultados_ativos.empty:
        return create_empty_figure(f"Dados para '{title}' indisponíveis.")
    if metric_col not in df_resultados_ativos.columns:
        return create_empty_figure(f"Coluna '{metric_col}' não encontrada para o gráfico '{title}'.")

    df_plot = df_resultados_ativos.dropna(subset=[metric_col]).copy()
    if df_plot.empty:
         return create_empty_figure(f"Sem dados válidos para '{metric_col}' no gráfico '{title}'.")

    df_sorted = df_plot.sort_values(by=metric_col, ascending=not higher_is_better)

    def format_text(x_val):
        if pd.isna(x_val): return 'N/A'
        # Se for uma métrica percentual e o sufixo for %, formatamos como percentual
        if y_axis_suffix == '%' and isinstance(x_val, (float, int)):
            return f'{x_val:.2f}%'
        # Para outros floats
        if isinstance(x_val, float):
            return f'{x_val:.2f}{y_axis_suffix}' 
        # Para inteiros
        if isinstance(x_val, int):
            return f'{int(x_val)}{y_axis_suffix}' 
        return str(x_val)

    bar_color = 'cornflowerblue' 
    if metric_col == 'Max_Drawdown_Percent':
        bar_color = 'lightcoral'
    elif not higher_is_better and metric_col != 'Max_Drawdown_Percent': 
        bar_color = 'lightseagreen'


    fig = go.Figure(data=[
        go.Bar(
            x=df_sorted['Asset'],
            y=df_sorted[metric_col],
            text=df_sorted[metric_col].apply(format_text),
            textposition='auto',
            marker_color=bar_color
        )
    ])

    y_title_base = metric_col.replace("_", " ").title()
    y_title = f"{y_title_base} {y_axis_suffix if y_axis_suffix != '%' else '(%)'}".strip()
    if "Percent" in metric_col and "(%)" not in y_title: 
        y_title = y_title_base.replace(" Percent", " (%)")


    fig.update_layout(
        title_text=title,
        xaxis_tickangle=-45,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font_color='white',
        yaxis_gridcolor='rgba(128,128,128,0.3)',
        xaxis_gridcolor='rgba(128,128,128,0.3)',
        margin=dict(l=40, r=20, t=60, b=120) 
    )
    fig.update_yaxes(title_text=y_title)
    return fig

# --- NOVAS FUNÇÕES PARA CURVA DE PATRIMÔNIO E TABELA DE TRADES ---

def plot_equity_curve(equity_curve_json_str: str, asset_name: str):
    """
    Gera o gráfico da curva de patrimônio a partir de uma string JSON.
    """
    if not equity_curve_json_str:
        print(f"DEBUG(plots.py): Curva de Patrimônio JSON para {asset_name} está vazia ou None.")
        return create_empty_figure(f"Curva de Patrimônio indisponível para {asset_name}.")
    
    try:
        # Usar io.StringIO para ler strings JSON para evitar FutureWarning
        df_equity = pd.read_json(io.StringIO(equity_curve_json_str), orient='split')
        # Garante que o índice é um datetime para plotagem correta
        df_equity.index = pd.to_datetime(df_equity.index)
        print(f"DEBUG(plots.py): Curva de Patrimônio para {asset_name} carregada com {len(df_equity)} pontos.")

        fig = go.Figure(data=[
            go.Scatter(x=df_equity.index, y=df_equity['Equity'], mode='lines', name='Patrimônio',
                       line=dict(color='lightgreen', width=2))
        ])

        fig.update_layout(
            title_text=f'Curva de Patrimônio para {asset_name}',
            xaxis_title='Data',
            yaxis_title='Patrimônio ($)',
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='white',
            xaxis_gridcolor='rgba(128,128,128,0.3)',
            yaxis_gridcolor='rgba(128,128,128,0.3)',
            margin=dict(l=40, r=20, t=60, b=40)
        )
        return fig
    except Exception as e:
        import traceback
        print(f"ERRO(plots.py): Falha ao plotar curva de patrimônio para {asset_name}: {e}")
        traceback.print_exc()
        return create_empty_figure(f"Erro ao carregar curva de patrimônio para {asset_name}.")

def get_trades_table_data(trades_json_str: str):
    """
    Prepara os dados e colunas para a dash_table.DataTable de trades.
    """
    if not trades_json_str:
        print("DEBUG(plots.py): Trades JSON está vazio ou None. Retornando [], [].")
        return [], [] # Retorna dados e colunas vazias
    
    try:
        # Usar io.StringIO para ler strings JSON para evitar FutureWarning
        df_trades = pd.read_json(io.StringIO(trades_json_str), orient='split')
        print(f"DEBUG(plots.py): df_trades carregado com {len(df_trades)} linhas. Colunas originais: {df_trades.columns.tolist()}")
        
        if df_trades.empty:
            print("DEBUG(plots.py): df_trades carregado está vazio após leitura do JSON.")
            return [], [] # Retorna vazio se o JSON foi lido mas o DataFrame é vazio
        
        # Backtesting.py trades DataFrame columns:
        # Ex: ['Size', 'EntryBar', 'ExitBar', 'EntryPrice', 'ExitPrice', 'SL', 'TP', 'PnL', 'ReturnPct', 'EntryTime', 'ExitTime', 'Duration', 'Tag']

        # Renomear colunas para nomes mais amigáveis no dashboard
        friendly_trade_col_names = {
            "EntryTime": "Entrada Tempo",
            "ExitTime": "Saída Tempo",
            "EntryPrice": "Entrada Preço",
            "ExitPrice": "Saída Preço",
            "Size": "Tamanho",
            "ReturnPct": "Retorno (%)",
            "PnL": "Lucro/Prejuízo ($)", # Mais descritivo
            "Duration": "Duração Trade", # Mais descritivo
            "Exposure": "Exposição", # Geralmente é um valor bruto, não %
            "Tag": "Tipo de Saída" # Se Tag é usado para stop/take-profit/exit
        }
        # Apenas renomeia colunas que existem no DataFrame
        df_trades = df_trades.rename(columns={k: v for k, v in friendly_trade_col_names.items() if k in df_trades.columns})
        print(f"DEBUG(plots.py): df_trades colunas após renomeio: {df_trades.columns.tolist()}")

        # --- MODIFICAÇÃO CHAVE AQUI: Formatar colunas de tempo para STRING antes de passar para a tabela ---
        for col_name_friendly in ["Entrada Tempo", "Saída Tempo"]:
            if col_name_friendly in df_trades.columns:
                # Converte para datetime primeiro, se ainda não for
                df_trades[col_name_friendly] = pd.to_datetime(df_trades[col_name_friendly], errors='coerce', utc=True)
                # Formata para string. Usamos .dt.strftime para um formato específico
                df_trades[col_name_friendly] = df_trades[col_name_friendly].dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')

        for col_name_friendly in ["Duração Trade", "Exposição"]:
            if col_name_friendly in df_trades.columns:
                df_trades[col_name_friendly] = df_trades[col_name_friendly].astype(str).fillna('')


        # Definir as colunas para a tabela Dash
        columns = []
        for col_id in df_trades.columns: # Itera sobre as colunas JÁ RENOMEADAS
            col_dict = {"name": col_id, "id": col_id}

            # Agora, TODAS as colunas de tempo são do TIPO 'text'
            if col_id in ["Entrada Tempo", "Saída Tempo", "Duração Trade", "Exposição", "Tipo de Saída"]:
                col_dict['type'] = 'text'
                # NÃO HÁ OBJETO 'format' PARA TIPO 'text', então removemos
            elif col_id == "Retorno (%)":
                col_dict['type'] = 'numeric'
                col_dict['format'] = Format(precision=2, scheme=Scheme.fixed).symbol(Symbol.yes).symbol_suffix('%')
            elif col_id == "Lucro/Prejuízo ($)":
                col_dict['type'] = 'numeric'
                col_dict['format'] = Format(precision=2, scheme=Scheme.fixed).symbol(Symbol.yes).symbol_prefix('$')
            elif col_id in ["Entrada Preço", "Saída Preço", "Tamanho"]:
                col_dict['type'] = 'numeric'
                col_dict['format'] = Format(precision=4, scheme=Scheme.fixed) 
            else: # Fallback para qualquer outra coluna
                col_dict['type'] = 'text'

            columns.append(col_dict)
        
        print(f"DEBUG(plots.py): {len(df_trades)} linhas e {len(columns)} colunas formatadas para a tabela de trades.")
        return df_trades.to_dict('records'), columns
    except Exception as e:
        import traceback # Importa aqui para ter certeza que está disponível
        print(f"ERRO(plots.py): Falha CRÍTICA ao processar dados de trades: {e}")
        traceback.print_exc() # Imprime o traceback completo para depuração
        return [], [] # Retorna vazio em caso de erro