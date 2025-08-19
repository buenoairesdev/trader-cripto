# dashboard_backtest/app.py
import dash
from dash import dcc, html, dash_table, Input, Output, State
from dash.dash_table.Format import Format, Scheme, Symbol # Para formatação de colunas
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
import json
import os # Importação adicionada

# Importe suas funções de consulta e plotagem
import db_queries
import plots

# Inicializa o aplicativo Dash
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
server = app.server

# --- CAMINHO PARA O ARQUIVO DE POSIÇÕES BYBIT ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))  # Diretório onde app.py está (ex: .../bot1/dashboard_backtest/)
PARENT_DIR_OF_APP = os.path.dirname(APP_DIR)         # Diretório pai (ex: .../bot1/)
POSICOES_BYBIT_JSON_FILE = os.path.join(PARENT_DIR_OF_APP, 'bybit_positions.json') # Caminho corrigido!

# --- CARREGAR DADOS INICIAIS (Backtest) ---
df_execucoes_disponiveis = db_queries.get_all_executions()

# --- DEFINIÇÕES GLOBAIS (Backtest) ---
FRIENDLY_COLUMN_NAMES = {
    "Asset": "Ativo",
    "Return_Percent": "Retorno (%)",
    "Sharpe_Ratio": "Sharpe Ratio",
    "Max_Drawdown_Percent": "Max Drawdown (%)",
    "Num_Trades": "Nº Trades",
    "Win_Rate_Percent": "Win Rate (%)",
    "Profit_Factor": "Profit Factor",
    "Estrategia_Descricao": "Config. Estratégia",
    "Buy_Hold_Return_Percent": "B&H Retorno (%)",
    "Sortino_Ratio": "Sortino Ratio",
    "Calmar_Ratio": "Calmar Ratio",
    "Avg_Trade_Percent": "Trade Médio (%)",
    "SQN": "SQN",
    "StartTime": "Início",
    "EndTime": "Fim",
    "Duration": "Duração",
    "Exposure_Time_Percent": "Tempo Exposto (%)",
    "Equity_Final": "Patrimônio Final ($)",
    "Equity_Peak": "Pico Patrimônio ($)",
    "Return_Ann_Percent": "Retorno Anual. (%)",
    "Volatility_Ann_Percent": "Volatilidade Anual. (%)",
    "Avg_Drawdown_Percent": "Drawdown Médio (%)",
    "Max_Drawdown_Duration": "Duração Max Drawdown",
    "Avg_Drawdown_Duration": "Duração Média Drawdown",
    "Best_Trade_Percent": "Melhor Trade (%)",
    "Worst_Trade_Percent": "Pior Trade (%)",
    "Max_Trade_Duration": "Duração Max Trade",
    "Avg_Trade_Duration": "Duração Média Trade",
    "Expectancy_Percent": "Expectativa (%)",
    "_strategy": "Nome Estratégia (Raw)",
    "Foi_Otimizado": "Otimizado?"
}

# --- DEFINIÇÕES PARA TABELA DE POSIÇÕES BYBIT ---
BYBIT_POSITIONS_COLUMNS_DISPLAY = {
    "symbol": "Símbolo", "side": "Lado", "size": "Tamanho", "leverage": "Alavancagem",
    "avgPrice": "Preço Médio", "markPrice": "Preço Atual",
    "unrealisedPnl": "P&L Não Real. (USDT)", "positionValue": "Valor Posição (USDT)",
    "liqPrice": "Preço Liq."
}
BYBIT_POSITIONS_COLUMN_ORDER = [
    "symbol", "side", "size", "leverage", "avgPrice", "markPrice",
    "unrealisedPnl", "positionValue", "liqPrice"
]


# Layout do aplicativo
app.layout = dbc.Container([
    dbc.Row(dbc.Col(html.H1("Dashboard de Análise de Backtests"),
            width=12, className="mb-4 mt-4 text-center")),
    dbc.Row(dbc.Col(html.H3("Execuções de Backtest Disponíveis"),
            width=12, className="mb-2")),
    dbc.Row(
        dbc.Col(
            dash_table.DataTable(
                id='tabela-execucoes',
                columns=[{"name": i, "id": i}
                         for i in df_execucoes_disponiveis.columns] if not df_execucoes_disponiveis.empty else [],
                data=df_execucoes_disponiveis.to_dict(
                    'records') if not df_execucoes_disponiveis.empty else [],
                row_selectable='single', selected_rows=[], page_size=10,
                style_header={
                    'backgroundColor': 'rgb(30, 30, 30)', 'color': 'white', 'fontWeight': 'bold'},
                style_cell={'backgroundColor': 'rgb(50, 50, 50)', 'color': 'white',
                            'border': '1px solid grey', 'textAlign': 'left'},
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgb(60, 60, 60)'}]
            ), width=12,
        )
    ),
    dbc.Row(dbc.Col(html.Hr(), width=12, className="mt-4 mb-4")),
    dbc.Row(dbc.Col(html.H3(id='titulo-detalhes-execucao'),
            width=12, className="mb-2")),
    dbc.Row([
        dbc.Col(id='sumario-execucao-selecionada', width=12, className="mb-3"),
        dbc.Col(
            dash_table.DataTable(
                id='tabela-resultados-ativos', columns=[], data=[], page_size=10,
                row_selectable='single', selected_rows=[],
                style_header={
                    'backgroundColor': 'rgb(30, 30, 30)', 'color': 'white', 'fontWeight': 'bold'},
                style_cell={'backgroundColor': 'rgb(50, 50, 50)', 'color': 'white',
                            'border': '1px solid grey', 'textAlign': 'left'},
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgb(60, 60, 60)'}],
                style_cell_conditional=[
                    {'if': {'column_id': 'Estrategia_Descricao'}, 'minWidth': '250px', 'width': '250px',
                        'maxWidth': '400px', 'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'normal'},
                    {'if': {'column_id': 'Asset'}, 'minWidth': '100px',
                        'width': '100px', 'maxWidth': '150px'}
                ]
            ), width=12
        )
    ]),
    dbc.Row(dbc.Col(html.Hr(), width=12, className="mt-4 mb-4")),
    dbc.Row(dbc.Col(html.H3(id='titulo-graficos-execucao'),
            width=12, className="mb-2")),
    dbc.Row([
        dbc.Col(dcc.Graph(id='grafico-retorno-comparativo',
                figure=plots.create_empty_figure()), width=12, lg=6),
        dbc.Col(dcc.Graph(id='grafico-sharpe-ratio',
                figure=plots.create_empty_figure()), width=12, lg=6)
    ]),
    dbc.Row([
        dbc.Col(dcc.Graph(id='grafico-max-drawdown',
                figure=plots.create_empty_figure()), width=12, lg=6),
        dbc.Col(dcc.Graph(id='grafico-num-trades',
                figure=plots.create_empty_figure()), width=12, lg=6)
    ]),
    dbc.Row([
        dbc.Col(dcc.Graph(id='grafico-win-rate',
                figure=plots.create_empty_figure()), width=12, lg=6),
        dbc.Col(dcc.Graph(id='grafico-profit-factor',
                figure=plots.create_empty_figure()), width=12, lg=6)
    ]),
    dbc.Row(dbc.Col(html.Hr(), width=12, className="mt-4 mb-4")),
    dbc.Row(dbc.Col(html.H3(id='titulo-detalhes-ativo'),
            width=12, className="mb-2")),
    dbc.Row(dbc.Col(id='sumario-detalhes-ativo', width=12, className="mb-3")),

    dbc.Row(dbc.Col(html.H4("Curva de Patrimônio"),
            width=12, className="mt-4 mb-2")),
    dbc.Row(dbc.Col(dcc.Graph(id='grafico-curva-patrimonio-ativo',
            figure=plots.create_empty_figure()), width=12, className="mb-4")),

    dbc.Row(dbc.Col(html.H4("Detalhes dos Trades"), width=12, className="mb-2")),
    dbc.Row(dbc.Col(
        dash_table.DataTable(
            id='tabela-trades-ativo',
            columns=[],
            data=[],
            page_size=10,
            style_header={
                'backgroundColor': 'rgb(30, 30, 30)', 'color': 'white', 'fontWeight': 'bold'},
            style_cell={'backgroundColor': 'rgb(50, 50, 50)', 'color': 'white',
                        'border': '1px solid grey', 'textAlign': 'left'},
            style_data_conditional=[
                {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgb(60, 60, 60)'}],
            style_cell_conditional=[
                {'if': {'column_id': 'Tag'}, 'minWidth': '150px', 'width': '150px', 'maxWidth': '300px',
                    'whiteSpace': 'normal', 'textOverflow': 'ellipsis', 'overflow': 'hidden'}
            ]
        ), width=12, className="mb-4"
    )),

    # --- NOVA SEÇÃO DE MONITORAMENTO DE POSIÇÕES BYBIT ---
    dbc.Row(dbc.Col(html.Hr(style={'borderColor': 'white', 'borderWidth': '2px', 'opacity': '0.75'}), 
            width=12, className="my-5")), # Divisor mais proeminente

    dbc.Row(dbc.Col(html.H2("Monitor de Posições Abertas Bybit"),
            width=12, className="mb-3 mt-2 text-center")),

    dbc.Row(
        dbc.Col(
            dash_table.DataTable(
                id='tabela-posicoes-bybit',
                columns=[], 
                data=[],    
                page_size=10,
                sort_action="native",
                filter_action="native",
                style_header={
                    'backgroundColor': 'rgb(30, 30, 30)', 'color': 'white', 'fontWeight': 'bold',
                    'textAlign': 'center'},
                style_cell={'backgroundColor': 'rgb(50, 50, 50)', 'color': 'white',
                            'border': '1px solid grey', 'textAlign': 'left',
                            'minWidth': '80px', 'width': '100px', 'maxWidth': '180px',
                            'overflow': 'hidden', 'textOverflow': 'ellipsis', 
                            'fontFamily': 'Arial, sans-serif'}, # Fonte mais legível
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': 'rgb(60, 60, 60)'},
                    {'if': {'filter_query': '{P&L Não Real. (USDT)} > 0', 
                            'column_id': 'P&L Não Real. (USDT)'},
                     'color': '#4CAF50', 'fontWeight': 'bold'}, # Verde para lucro
                    {'if': {'filter_query': '{P&L Não Real. (USDT)} < 0', 
                            'column_id': 'P&L Não Real. (USDT)'},
                     'color': '#F44336', 'fontWeight': 'bold'}  # Vermelho para prejuízo
                ],
                style_cell_conditional=[
                    {'if': {'column_id': 'Símbolo'}, 'minWidth': '100px', 'fontWeight': 'bold', 'textAlign': 'center'},
                    {'if': {'column_id': 'Lado'}, 'minWidth': '70px', 'textAlign': 'center'},
                    {'if': {'column_id': 'Alavancagem'}, 'textAlign': 'center'},
                    {'if': {'column_id': 'P&L Não Real. (USDT)'}, 'minWidth': '160px', 'textAlign': 'right'},
                    {'if': {'column_id': 'Valor Posição (USDT)'}, 'minWidth': '160px', 'textAlign': 'right'},
                    {'if': {'column_id': 'Preço Médio'}, 'textAlign': 'right'},
                    {'if': {'column_id': 'Preço Atual'}, 'textAlign': 'right'},
                    {'if': {'column_id': 'Preço Liq.'}, 'textAlign': 'right'},
                    {'if': {'column_id': 'Tamanho'}, 'textAlign': 'right'},
                ]
            ), width=12, className="mb-4"
        )
    ),
    dcc.Interval(
        id='intervalo-atualizacao-bybit',
        interval=7 * 1000,  # 7 segundos
        n_intervals=0
    ),
    # --- FIM DA NOVA SEÇÃO ---

], fluid=True)


# --- CALLBACKS EXISTENTES (Backtest) ---
@app.callback(
    [Output('sumario-execucao-selecionada', 'children'),
     Output('tabela-resultados-ativos',
            'data'), Output('tabela-resultados-ativos', 'columns'),
     Output('grafico-retorno-comparativo',
            'figure'), Output('grafico-sharpe-ratio', 'figure'),
     Output('grafico-max-drawdown',
            'figure'), Output('grafico-num-trades', 'figure'),
     Output('grafico-win-rate', 'figure'), Output('grafico-profit-factor', 'figure'),
     Output('titulo-detalhes-execucao',
            'children'), Output('titulo-graficos-execucao', 'children'),
     Output('tabela-resultados-ativos', 'selected_rows', allow_duplicate=True),
     Output('titulo-detalhes-ativo', 'children', allow_duplicate=True),
     Output('sumario-detalhes-ativo', 'children', allow_duplicate=True)],
    [Input('tabela-execucoes', 'selected_rows')],
    [State('tabela-execucoes', 'data')],
    prevent_initial_call=True
)
def update_execution_details(selected_rows, rows_data):
    if not selected_rows:
        empty_fig = plots.create_empty_figure()
        no_sel_asset_title = "Detalhes do Ativo"
        no_sel_asset_sumario = html.Div(html.P(
            "Selecione um ativo na tabela acima para ver seus detalhes completos."), className="text-center p-3")
        return (html.Div(html.P("Selecione uma execução na tabela acima para ver os detalhes."), className="text-center p-3"),
                [], [], empty_fig, empty_fig, empty_fig, empty_fig, empty_fig, empty_fig,
                "Detalhes da Execução", "Gráficos da Execução", [], no_sel_asset_title, no_sel_asset_sumario)

    selected_execution_id = rows_data[selected_rows[0]]['id_execucao']
    dados_exec = db_queries.get_execution_details(selected_execution_id)
    sumario_children = []
    if not dados_exec.empty:
        sumario_children.append(html.H4(
            f"Parâmetros da Execução ID: {selected_execution_id}", className="mt-3 mb-3"))
        list_group_items = []
        for k, v_scalar in dados_exec.items():
            if k == 'id_execucao':
                continue
            valor_display_final, item_style = "", {}
            is_missing_value = False
            actual_value_to_process = v_scalar
            if isinstance(v_scalar, pd.Series):
                if v_scalar.empty: is_missing_value = True
                elif v_scalar.isna().all(): is_missing_value = True
                else:
                    try:
                        actual_value_to_process = v_scalar.item(); is_missing_value = pd.isna(actual_value_to_process)
                    except ValueError:
                        actual_value_to_process = str(v_scalar.to_list()); is_missing_value = False
            elif isinstance(v_scalar, (list, dict)): is_missing_value = False
            else: is_missing_value = pd.isna(v_scalar)

            if is_missing_value: valor_display_final = html.Span("N/A", style={'fontStyle': 'italic'})
            elif isinstance(actual_value_to_process, list): valor_display_final = html.Span(", ".join(map(str, actual_value_to_process)) if actual_value_to_process else "N/A")
            elif isinstance(actual_value_to_process, dict):
                valor_display_final = html.Pre(json.dumps(actual_value_to_process, indent=2, ensure_ascii=False),
                                               style={'whiteSpace': 'pre-wrap', 'wordBreak': 'break-all', 'backgroundColor': '#222529',
                                                      'padding': '10px', 'borderRadius': '5px', 'color': '#e9ecef',
                                                      'fontSize': '0.85em', 'maxHeight': '200px', 'overflowY': 'auto'})
            else:
                valor_display_final = html.Span(str(actual_value_to_process))
                if k.lower() == 'descricao' and len(str(actual_value_to_process)) > 100:
                    item_style = {'whiteSpace': 'pre-wrap', 'wordBreak': 'break-all', 'maxHeight': '150px', 'overflowY': 'auto'}
            list_group_items.append(dbc.ListGroupItem([dbc.Row([dbc.Col(html.Strong(f"{k.replace('_', ' ').capitalize()}:"), width=12, md=3, className="text-md-end text-start fw-bold"), dbc.Col(html.Div(valor_display_final, style=item_style), width=12, md=9)], align="start", className="py-1")], className="bg-transparent border-0 px-0"))
        sumario_children.append(dbc.ListGroup(list_group_items, flush=True, className="mb-3"))
    else: sumario_children.append(html.P("Detalhes da execução não encontrados."))

    df_ativos = db_queries.get_asset_results_for_execution(selected_execution_id)
    colunas_formatadas_tabela_ativos, df_ativos_para_tabela = [], pd.DataFrame()
    if not df_ativos.empty:
        cols_disp = ['Asset', 'Return_Percent', 'Sharpe_Ratio', 'Max_Drawdown_Percent', 'Num_Trades', 'Win_Rate_Percent', 'Profit_Factor', 'Estrategia_Descricao']
        cols_exist_ord = [c for c in cols_disp if c in df_ativos.columns]
        for col_id in cols_exist_ord:
            col_name = FRIENDLY_COLUMN_NAMES.get(col_id, col_id.replace("_", " ").title())
            col_dict = {"name": col_name, "id": col_id, "selectable": False}
            if "_Percent" in col_id: col_dict['type'], col_dict['format'] = 'numeric', Format(precision=2, scheme=Scheme.fixed).symbol(Symbol.yes).symbol_suffix('%')
            elif col_id in ["Sharpe_Ratio", "Profit_Factor", "Sortino_Ratio", "Calmar_Ratio", "SQN"]: col_dict['type'], col_dict['format'] = 'numeric', Format(precision=2, scheme=Scheme.fixed)
            elif col_id == "Num_Trades": col_dict['type'], col_dict['format'] = 'numeric', Format(precision=0, scheme=Scheme.fixed)
            elif col_id in ['Asset', 'Estrategia_Descricao']: col_dict['type'] = 'text'
            colunas_formatadas_tabela_ativos.append(col_dict)
        df_ativos_para_tabela = df_ativos[cols_exist_ord].copy()

    fig_retorno, fig_sharpe, fig_max_dd, fig_num_trades, fig_win_rate, fig_profit_factor = [plots.create_empty_figure()]*6
    titulo_det_exec, titulo_graf_exec = f"Detalhes da Execução ID: {selected_execution_id}", f"Gráficos da Execução ID: {selected_execution_id}"
    if not df_ativos.empty:
        fig_retorno = plots.plot_retorno_comparativo(df_ativos)
        fig_sharpe = plots.plot_generic_metric_bar(df_ativos, 'Sharpe_Ratio', 'Sharpe Ratio por Ativo', True)
        fig_max_dd = plots.plot_generic_metric_bar(df_ativos, 'Max_Drawdown_Percent', 'Max Drawdown (%) por Ativo', False, y_axis_suffix='%')
        fig_num_trades = plots.plot_generic_metric_bar(df_ativos, 'Num_Trades', 'Número de Trades por Ativo', True)
        fig_win_rate = plots.plot_generic_metric_bar(df_ativos, 'Win_Rate_Percent', 'Win Rate (%) por Ativo', True, y_axis_suffix='%')
        fig_profit_factor = plots.plot_generic_metric_bar(df_ativos, 'Profit_Factor', 'Profit Factor por Ativo', True)
    else:
        empty_fig_msg = plots.create_empty_figure(f"Sem dados de ativos para a execução {selected_execution_id}")
        fig_retorno, fig_sharpe, fig_max_dd, fig_num_trades, fig_win_rate, fig_profit_factor = [empty_fig_msg]*6
        titulo_det_exec += " (Sem resultados de ativos)"; titulo_graf_exec += " (Sem resultados de ativos)"
    no_sel_asset_title = "Detalhes do Ativo"
    no_sel_asset_sumario = html.Div(html.P("Selecione um ativo na tabela acima para ver seus detalhes completos."), className="text-center p-3")
    return (sumario_children, df_ativos_para_tabela.to_dict('records') if not df_ativos_para_tabela.empty else [],
            colunas_formatadas_tabela_ativos if not df_ativos_para_tabela.empty else [],
            fig_retorno, fig_sharpe, fig_max_dd, fig_num_trades, fig_win_rate, fig_profit_factor,
            titulo_det_exec, titulo_graf_exec, [], no_sel_asset_title, no_sel_asset_sumario)

@app.callback(
    [Output('titulo-detalhes-ativo', 'children', allow_duplicate=True),
     Output('sumario-detalhes-ativo', 'children', allow_duplicate=True),
     Output('grafico-curva-patrimonio-ativo', 'figure'),
     Output('tabela-trades-ativo', 'data'),
     Output('tabela-trades-ativo', 'columns')],
    [Input('tabela-resultados-ativos', 'selected_rows')],
    [State('tabela-resultados-ativos', 'data'), State('tabela-execucoes', 'selected_rows'), State('tabela-execucoes', 'data')],
    prevent_initial_call=True
)
def update_asset_details(selected_asset_rows, asset_rows_data, selected_exec_rows, exec_rows_data):
    default_title = "Detalhes do Ativo"
    default_summary = html.Div(html.P("Selecione uma execução e depois um ativo para ver seus detalhes completos."), className="text-center p-3")
    empty_figure = plots.create_empty_figure(); empty_trades_data = []; empty_trades_cols = []
    if not selected_asset_rows or not asset_rows_data or not selected_exec_rows:
        return default_title, default_summary, empty_figure, empty_trades_data, empty_trades_cols
    selected_asset_name = asset_rows_data[selected_asset_rows[0]].get('Asset')
    selected_execution_id = exec_rows_data[selected_exec_rows[0]]['id_execucao']
    if not selected_asset_name or not selected_execution_id:
        return default_title, default_summary, empty_figure, empty_trades_data, empty_trades_cols
    df_todos_ativos_exec = db_queries.get_asset_results_for_execution(selected_execution_id)
    if df_todos_ativos_exec.empty:
        return f"Detalhes de {selected_asset_name}", html.P(f"Dados não encontrados para ativo {selected_asset_name} na exec {selected_execution_id}."), empty_figure, empty_trades_data, empty_trades_cols
    asset_data_series = df_todos_ativos_exec[df_todos_ativos_exec['Asset'] == selected_asset_name]
    if asset_data_series.empty:
        return f"Detalhes de {selected_asset_name}", html.P(f"Dados detalhados não encontrados para ativo {selected_asset_name} na exec {selected_execution_id}."), empty_figure, empty_trades_data, empty_trades_cols
    asset_details = asset_data_series.iloc[0]
    titulo_secao_ativo = f"Análise Detalhada: {selected_asset_name} (Execução ID: {selected_execution_id})"
    list_group_items_asset = []
    equity_curve_json = asset_details.get('EquityCurve_JSON'); trades_json = asset_details.get('Trades_JSON')
    fig_equity_curve = plots.plot_equity_curve(equity_curve_json, selected_asset_name)
    trades_data, trades_columns = plots.get_trades_table_data(trades_json)
    keys_to_exclude_from_summary = ['id_execucao', 'id_resultado', 'Asset', 'EquityCurve_JSON', 'Trades_JSON']
    for k_orig, v_scalar in asset_details.items():
        if k_orig in keys_to_exclude_from_summary: continue
        col_name_friendly, valor_display_final, item_style = FRIENDLY_COLUMN_NAMES.get(k_orig, k_orig.replace("_", " ").title()), "", {}
        is_missing_value = False; actual_value_to_process = v_scalar
        if isinstance(v_scalar, pd.Series):
            if v_scalar.empty or v_scalar.isna().all(): is_missing_value = True
            else:
                try: actual_value_to_process = v_scalar.item(); is_missing_value = pd.isna(actual_value_to_process)
                except ValueError: actual_value_to_process = str(v_scalar.to_list()); is_missing_value = False
        else: is_missing_value = pd.isna(v_scalar)
        if is_missing_value: valor_display_final = html.Span("N/A", style={'fontStyle': 'italic'})
        elif isinstance(actual_value_to_process, float): valor_display_final = html.Span(f"{actual_value_to_process:.2f}{'%' if '_Percent' in k_orig else ''}")
        elif isinstance(actual_value_to_process, int) and k_orig == "Num_Trades": valor_display_final = html.Span(f"{actual_value_to_process}")
        elif isinstance(actual_value_to_process, (bool, pd.BooleanDtype)): valor_display_final = html.Span("Sim" if actual_value_to_process else "Não")
        else:
            valor_display_final = html.Span(str(actual_value_to_process))
            if (k_orig.lower() in ['estrategia_descricao', '_strategy']) and len(str(actual_value_to_process)) > 100:
                item_style = {'whiteSpace': 'pre-wrap', 'wordBreak': 'break-all', 'maxHeight': '150px', 'overflowY': 'auto'}
        list_group_items_asset.append(dbc.ListGroupItem([dbc.Row([dbc.Col(html.Strong(f"{col_name_friendly}:"), width=12, md=4, className="text-md-end text-start fw-bold"), dbc.Col(html.Div(valor_display_final, style=item_style), width=12, md=8)], align="start", className="py-1")], className="bg-transparent border-0 px-0"))
    sumario_ativo_children = dbc.Card(dbc.CardBody([dbc.ListGroup(list_group_items_asset, flush=True, className="mt-1")]))
    return titulo_secao_ativo, sumario_ativo_children, fig_equity_curve, trades_data, trades_columns

# --- NOVO CALLBACK PARA ATUALIZAR TABELA DE POSIÇÕES BYBIT ---
@app.callback(
    [Output('tabela-posicoes-bybit', 'data'),
     Output('tabela-posicoes-bybit', 'columns')],
    [Input('intervalo-atualizacao-bybit', 'n_intervals')]
)
def update_bybit_positions_live_table(n_intervals):
    positions_data = []
    try:
        if os.path.exists(POSICOES_BYBIT_JSON_FILE):
            with open(POSICOES_BYBIT_JSON_FILE, 'r') as f:
                try:
                    positions_data = json.load(f) 
                except json.JSONDecodeError:
                    print(f"Dash Aviso: Erro ao decodificar {POSICOES_BYBIT_JSON_FILE}. O arquivo pode estar sendo escrito ou corrompido.")
                    positions_data = [] 
        # else:
            # Opcional: print(f"Dash Aviso: Arquivo {POSICOES_BYBIT_JSON_FILE} não encontrado nesta atualização ({n_intervals}).")
            # Se o arquivo não existe, positions_data continuará como []
    except Exception as e:
        print(f"Dash Erro: Erro ao ler o arquivo de posições Bybit ({POSICOES_BYBIT_JSON_FILE}): {e}")
        positions_data = []

    if not isinstance(positions_data, list): # Garante que é uma lista, mesmo que vazia
        if positions_data is not None: # Log apenas se não for None mas não for lista
             print(f"Dash Aviso: Dados lidos de {POSICOES_BYBIT_JSON_FILE} não são uma lista. Conteúdo: {type(positions_data)}")
        positions_data = []

    columns_for_table = []
    for col_id in BYBIT_POSITIONS_COLUMN_ORDER:
        col_name = BYBIT_POSITIONS_COLUMNS_DISPLAY.get(col_id, col_id.title())
        col_dict = {"name": col_name, "id": col_id}
        
        if col_id in ["size", "avgPrice", "markPrice", "unrealisedPnl", "positionValue", "liqPrice"]:
            col_dict['type'] = 'numeric'
            if col_id in ["unrealisedPnl", "positionValue"]:
                col_dict['format'] = Format(precision=2, scheme=Scheme.fixed)
            elif col_id in ["avgPrice", "markPrice", "liqPrice"]:
                # Precisão pode variar. 2 é um bom default, 4 para pares com mais casas.
                col_dict['format'] = Format(precision=4, scheme=Scheme.fixed) 
            elif col_id == "size":
                col_dict['format'] = Format(precision=6, scheme=Scheme.fixed)
        else: # side, symbol, leverage
            col_dict['type'] = 'text'
        columns_for_table.append(col_dict)
            
    processed_data = []
    if positions_data:
        for row_dict_orig in positions_data:
            # Garante que apenas as colunas esperadas estão presentes e na ordem correta
            new_row = {key: row_dict_orig.get(key) for key in BYBIT_POSITIONS_COLUMN_ORDER}
            try:
                # Converte P&L para float para que a formatação condicional de cor funcione corretamente
                if 'unrealisedPnl' in new_row and new_row['unrealisedPnl'] is not None:
                    new_row['unrealisedPnl'] = float(new_row['unrealisedPnl'])
            except (ValueError, TypeError):
                new_row['unrealisedPnl'] = None # Ou 0, se preferir que apareça neutro
            processed_data.append(new_row)
            
    return processed_data, columns_for_table

if __name__ == '__main__':
    app.run(debug=True)