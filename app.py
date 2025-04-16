import dash
from dash import html, dcc, Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import requests
import time
import hmac
import hashlib
import base64
from urllib.parse import urlencode
import plotly.express as px
from dash import dash_table
from datetime import datetime
import os

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

app.title = "Bitcoin 10X Dashboard"

custom_theme = {
    'dark': False,
    'primary': '#F29727',
    'secondary': '#F2AE2E',
    'background': '#0C2031',
    'font_color': '#FFFFFF',
    'accent': '#F27F1B',
    'border': '#8C5B30'
}

app.layout = dbc.Container([
    dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand("Relatório Bitcoin 10X - Dashboard - Período de Testes até dia 20/04", className="text-white fw-bold mx-auto", style={"fontSize": "30px"})
        ]),
        color="orange",
        dark=True,
        className="mb-4 justify-content-center"
    ),

    dbc.Row([
        dbc.Col([
            dbc.Input(id='api_key', type='text', placeholder='Insira sua API Key', className='mb-2', autoComplete='off', persistence=True, persistence_type='local'),
            dbc.Input(id='api_secret', type='password', placeholder='Insira sua API Secret', className='mb-2', autoComplete='new-password', persistence=True, persistence_type='local'),
            dbc.Input(id='passphrase', type='text', placeholder='Insira sua Passphrase', className='mb-2', autoComplete='off', persistence=True, persistence_type='local'),
            dbc.Button("Consultar", id='load_data', color='warning', className='mb-4 w-100 fw-bold'),
            dcc.DatePickerRange(
                id='date_filter',
                display_format='DD/MM/YYYY',
                className='mb-2',
                style={'color': 'black'}
            )
        ], width=6)
    ], justify="center", className="mb-4"),

    html.Div(id='cards_container'),
    html.Div(id='graph_bar_container'),
    html.Div(id='table_container'),
    html.Div(id='graph_container'),
    html.Div(id='open_table_container')
], fluid=True, style={'backgroundColor': custom_theme['background'], 'color': custom_theme['font_color'], 'paddingBottom': '50px'})

def fetch_data(api_key, api_secret, passphrase, trade_type):
    base_url = "https://api.lnmarkets.com"
    path = "/v2/futures"
    url = f"{base_url}{path}"
    method = "GET"
    params = {"type": trade_type}

    timestamp = str(int(time.time() * 1000))
    query_string = urlencode(params)
    prehash_string = f"{timestamp}{method}{path}{query_string}"

    signature = base64.b64encode(
        hmac.new(api_secret.encode(), prehash_string.encode(), hashlib.sha256).digest()
    ).decode()

    headers = {
        "LNM-ACCESS-KEY": api_key,
        "LNM-ACCESS-SIGNATURE": signature,
        "LNM-ACCESS-PASSPHRASE": passphrase,
        "LNM-ACCESS-TIMESTAMP": timestamp
    }

    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        return "Credenciais inválidas"  # Mensagem de erro para credenciais inválidas    
    
    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame(data)

        if trade_type == "closed":
            df = df[df["closed"] == True]
        else:
            df = df[df["running"] == True]

        df['total_fee'] = df['sum_carry_fees'] + df['opening_fee'] + df['closing_fee']
        df['net_pl'] = df['pl'] - df['total_fee']
        df['net_profit'] = (df['net_pl'] / df['margin']) * 100

        df['closed_ts'] = pd.to_datetime(df['closed_ts'] / 1000, unit='s', errors='coerce')
        df['market_filled_ts'] = pd.to_datetime(df['market_filled_ts'] / 1000, unit='s', errors='coerce')

        df = df.sort_values(by='closed_ts', na_position='last')
        df['net_pl_acum'] = df['net_pl'].cumsum()

        df['net_profit'] = df['net_profit'].round(2)
        df['leverage'] = df['leverage'].round(2)

        df = df.reindex([
            "quantity", "margin", "entry_price", "exit_price", "market_filled_ts",
            "closed_ts", "leverage", "pl", "total_fee", "net_pl", 'net_profit', "net_pl_acum"
        ], axis=1)

        df = df.rename(columns={
            'quantity': 'Valor (USD)',
            'margin': 'Margem',
            'entry_price': 'Preço Inicial',
            'exit_price': 'Preço Final',
            'market_filled_ts': 'Data Inicial',
            'closed_ts': 'Data Final',
            'leverage': 'Alavancagem',
            'pl': 'Lucro (sats)',
            'total_fee': 'Taxas',
            'net_pl': 'Lucro Líquido (sats)',
            'net_profit': 'Rentabilidade (%)',
            'net_pl_acum': 'Lucro Acumulado'
        })

        df['Data Inicial'] = pd.to_datetime(df['Data Inicial'], errors='coerce').dt.strftime('%d/%m/%Y')
        df['Data Final'] = pd.to_datetime(df['Data Final'], errors='coerce').dt.strftime('%d/%m/%Y')

        return df
    else:
        return pd.DataFrame()

@app.callback(
    Output('table_container', 'children'),
    Output('date_filter', 'min_date_allowed'),
    Output('date_filter', 'max_date_allowed'),
    Output('cards_container', 'children'),
    Output('open_table_container', 'children'),
    Output('graph_container', 'children'),
    Output('graph_bar_container', 'children'),
    Input('load_data', 'n_clicks'),
    State('api_key', 'value'),
    State('api_secret', 'value'),
    State('passphrase', 'value'),
    State('date_filter', 'start_date'),
    State('date_filter', 'end_date')
)
def update_dashboard(n_clicks, api_key, api_secret, passphrase, start_date, end_date):
    if not n_clicks:
        return html.P("🔒 Insira suas credenciais e clique em CONSULTAR para carregar os dados.", style={"fontSize": "28px"}), None, None, None, None, None, None

    if not api_key or not api_secret or not passphrase:
        return html.P("🔒 Insira suas credenciais de API acima.", style={"fontSize": "28px"}), None, None, None, None, None, None

    df = fetch_data(api_key, api_secret, passphrase, "closed")

    # Caso as credenciais sejam inválidas, exibe a mensagem de erro
    if isinstance(df, str) and df == "Credenciais inválidas":
        return html.P("❌ Credenciais inválidas. Verifique suas credenciais.", style={"fontSize": "28px"}), None, None, None, None, None, None

    df_open = fetch_data(api_key, api_secret, passphrase, "running")

    # Verificando se há dados para o período selecionado
    if df.empty and df_open.empty:
        return html.P("❌ Não há dados para o período selecionado.", style={"fontSize": "28px"}), None, None, None, None, None, None

    df['Data Final DT'] = pd.to_datetime(df['Data Final'], format='%d/%m/%Y')

    min_date = datetime(2025, 1, 1).date()
    max_date = datetime.today().date()

    # Aplicando o filtro de data
    if start_date:
        df = df[df['Data Final DT'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['Data Final DT'] <= pd.to_datetime(end_date)]

    # Verificando se o DataFrame está vazio após o filtro de data
    if df.empty:
        return html.P(f"❌ Não há dados para o período selecionado", style={"fontSize": "28px"}), None, None, None, None, None, None

    total_orders = df.shape[0]
    total_gains = df[df['Lucro Líquido (sats)'] >= 0].shape[0]
    total_losses = df[df['Lucro Líquido (sats)'] < 0].shape[0]
    winrate = (total_gains / total_orders * 100) if total_orders else 0

    cards = html.Div([
        html.H4("📊 Resumo"),
        dbc.Row([  # Cartões de resumo
            dbc.Col(dbc.Card([  # Cartão de Lucro Total
                dbc.CardHeader("Lucro total (satoshis)", className="fs-5 fw-bold"),
                dbc.CardBody(html.H4(f"{df['Lucro (sats)'].sum():,.0f}", className="fw-bold"))
            ], color="orange", inverse=True), width=3),
            dbc.Col(dbc.Card([  # Cartão de Total de Taxas
                dbc.CardHeader("Total de taxas (satoshis)", className="fs-5 fw-bold"),
                dbc.CardBody(html.H4(f"{df['Taxas'].sum():,.0f}", className="fw-bold"))
            ], color="secondary", inverse=True), width=3),
            dbc.Col(dbc.Card([  # Cartão de Lucro Líquido
                dbc.CardHeader("Lucro líquido (satoshis)", className="fs-5 fw-bold"),
                dbc.CardBody(html.H4(f"{df['Lucro Líquido (sats)'].sum():,.0f}", className="fw-bold"))
            ], color="orange", inverse=True), width=3),
            dbc.Col(dbc.Card([  # Cartão de Rentabilidade Média
                dbc.CardHeader("Rentabilidade média", className="fs-5 fw-bold"),
                dbc.CardBody(html.H4(f"{df['Rentabilidade (%)'].mean():.2f}%", className="fw-bold"))
            ], color="info", inverse=True), width=3),
        ], className="mb-4"),
        html.Br(),
        dbc.Row([  # Cartões de total de ordens
            dbc.Col(dbc.Card([  # Cartão de Total de Ordens
                dbc.CardHeader("Total de Ordens", className="fs-5 fw-bold"),
                dbc.CardBody(html.H4(f"{total_orders}", className="fw-bold"))
            ], color="dark", inverse=True), width=3),
            dbc.Col(dbc.Card([  # Cartão de Ganhos
                dbc.CardHeader("Ganhos", className="fs-5 fw-bold"),
                dbc.CardBody(html.H4(f"{total_gains}", className="fw-bold"))
            ], color="success", inverse=True), width=3),
            dbc.Col(dbc.Card([  # Cartão de Perdas
                dbc.CardHeader("Perdas", className="fs-5 fw-bold"),
                dbc.CardBody(html.H4(f"{total_losses}", className="fw-bold"))
            ], color="danger", inverse=True), width=3),
            dbc.Col(dbc.Card([  # Cartão de Aproveitamento
                dbc.CardHeader("Aproveitamento", className="fs-5 fw-bold"),
                dbc.CardBody(html.H4(f"{winrate:.2f}%", className="fw-bold"))
            ], color="info", inverse=True), width=3),
        ], className="mb-4")
    ])

    # Gráfico de Lucro Acumulado ao Longo do Tempo
    df_graph = df.groupby('Data Final DT', as_index=False)['Lucro Acumulado'].max()
    full_range = pd.date_range(df_graph['Data Final DT'].min(), df_graph['Data Final DT'].max())
    df_graph = df_graph.set_index('Data Final DT').reindex(full_range).rename_axis('Data Final DT').fillna(method='ffill').reset_index()
    df_graph['Data Final'] = df_graph['Data Final DT'].dt.strftime('%d/%m')

    fig_line = px.line(df_graph, x="Data Final", y="Lucro Acumulado", markers=True)
    fig_line.update_traces(line_shape='spline', line=dict(color='#F29727'))
    fig_line.update_layout(
        xaxis=dict(color='#FFFFFF', showgrid=False),
        yaxis=dict(color='#FFFFFF', showticklabels=False, showgrid=False),
        plot_bgcolor=custom_theme['background'],
        paper_bgcolor=custom_theme['background'],
        font=dict(color='#FFFFFF'),
        margin=dict(l=40, r=40, t=30, b=40)
    )

    graph_line = html.Div([
        html.H4("📈 Lucro Acumulado ao Longo do Tempo"),
        dcc.Graph(figure=fig_line, config={"displayModeBar": False})
    ])

    # Gráfico de barras - Lucro Total por Mês
    df_monthly = df.groupby(df['Data Final DT'].dt.to_period('M')).agg({'Lucro (sats)': 'sum'}).reset_index()
    df_monthly['Data Final'] = df_monthly['Data Final DT'].dt.strftime('%b %Y')  # Exibe o nome do mês e ano

    # Tradução dos meses para português
    month_translation = {
        'Jan': 'Jan', 'Feb': 'Fev', 'Mar': 'Mar', 'Apr': 'Abr', 'May': 'Mai', 'Jun': 'Jun',
        'Jul': 'Jul', 'Aug': 'Ago', 'Sep': 'Set', 'Oct': 'Out', 'Nov': 'Nov', 'Dec': 'Dez'
    }
    df_monthly['Data Final'] = df_monthly['Data Final'].apply(lambda x: month_translation[x[:3]] + x[3:])

    # Criando o gráfico de barras com cor laranja e sem gradiente
    fig_bar = px.bar(df_monthly, x="Data Final", y="Lucro (sats)", color_discrete_sequence=['#F29727'])  # Cor laranja

    # Adicionando rótulos de dados nas barras com a cor branca
    fig_bar.update_traces(text=df_monthly['Lucro (sats)'].apply(lambda x: f'{x:,.0f}'),
                        textposition='outside',  # Posiciona o texto fora das barras
                        textfont=dict(size=12, color='white'))  # Rótulo em branco

    # Removendo o gradiente de valor
    fig_bar.update_traces(marker=dict(color='#F29727'))  # Cor sólida laranja

    # Alterando o tamanho do gráfico e centralizando
    fig_bar.update_layout(
        width=600,  # Diminui o tamanho pela metade
        height=400,  # Diminui o tamanho pela metade
        margin=dict(l=40, r=40, t=40, b=40),  # Ajustando a margem para centralizar o gráfico
        xaxis=dict(color='#FFFFFF', showgrid=False, title='', tickmode='array', tickvals=df_monthly['Data Final'], ticktext=df_monthly['Data Final']),
        yaxis=dict(color='#FFFFFF', showgrid=False, title='', showticklabels=True),
        plot_bgcolor=custom_theme['background'],
        paper_bgcolor=custom_theme['background'],
        font=dict(color='#FFFFFF'),
    )

    # Exibindo o gráfico
    graph_bar = html.Div([
        html.H4("📊 Lucro Total por Mês"),
        dcc.Graph(figure=fig_bar, config={"displayModeBar": False})
    ])

    df = df.drop(columns=['Data Final DT'], errors='ignore')

    # Verificando ordens abertas (df_open) e retornando aviso caso esteja vazio
    if df_open.empty:
        open_table = html.Div([
            html.H4("📌 Ordens Abertas"),
            html.P("❌ Não há ordens abertas.", style={"fontSize": "28px"})
        ])
    else:
        df_open = df_open.drop(columns=['Data Final DT'], errors='ignore')
        open_table = html.Div([
            html.H4("📌 Ordens Abertas"),
            dash_table.DataTable(
                data=df_open.to_dict('records'),
                columns=[{"name": i, "id": i} for i in df_open.columns],
                style_table={'overflowX': 'auto'},
                style_cell={'backgroundColor': custom_theme['background'], 'color': custom_theme['font_color']},
                style_header={'backgroundColor': custom_theme['accent'], 'color': 'white', 'fontWeight': 'bold'},
                sort_action='native',
                filter_action='none'
            )
        ])

    # Verificando ordens fechadas (df) e retornando aviso caso esteja vazio
    if df.empty:
        table = html.Div([
            html.H4("📁 Ordens Fechadas"),
            html.P("❌ Não há ordens fechadas.", style={"fontSize": "28px"})
        ])
    else:
        table = html.Div([
            html.H4("📁 Ordens Fechadas"),
            dash_table.DataTable(
                data=df.to_dict('records'),
                columns=[{"name": i, "id": i} for i in df.columns],
                style_table={'overflowX': 'auto'},
                style_cell={'backgroundColor': custom_theme['background'], 'color': '#FFFFFF'},
                style_header={'backgroundColor': custom_theme['accent'], 'color': 'white', 'fontWeight': 'bold'},
                sort_action='native',
                filter_action='none'
            )
        ])

    return table, min_date, max_date, cards, open_table, graph_line, graph_bar


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
