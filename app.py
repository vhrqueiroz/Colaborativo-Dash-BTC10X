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
            dbc.NavbarBrand("Relatório Bitcoin 10X - Dashboard - Período de Testes até dia 15/04", className="text-white fw-bold mx-auto", style={"fontSize": "28px"})
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
    Input('load_data', 'n_clicks'),
    State('api_key', 'value'),
    State('api_secret', 'value'),
    State('passphrase', 'value'),
    State('date_filter', 'start_date'),
    State('date_filter', 'end_date')
)
def update_dashboard(n_clicks, api_key, api_secret, passphrase, start_date, end_date):
    if not n_clicks:
        return html.P("🔒 Insira suas credenciais e clique em CONSULTAR para carregar os dados.", style={"fontSize": "18px"}), datetime(2025, 1, 1).date(), datetime.today().date(), None, None, None

    if not api_key or not api_secret or not passphrase:
        return html.P("🔒 Insira suas credenciais de API acima.", style={"fontSize": "18px"}), datetime(2025, 1, 1).date(), datetime.today().date(), None, None, None

    df = fetch_data(api_key, api_secret, passphrase, "closed")
    df_open = fetch_data(api_key, api_secret, passphrase, "running")

    if df.empty and df_open.empty:
        return html.P("❌ Nenhum dado retornado da API para ordens fechadas ou abertas.", style={"fontSize": "18px"}), datetime(2025, 1, 1).date(), datetime.today().date(), None, None, None

    min_date = datetime(2025, 1, 1).date()
    max_date = datetime.today().date()

    if not df.empty:
        df['Data Final DT'] = pd.to_datetime(df['Data Final'], format='%d/%m/%Y', errors='coerce')
        df['Data Inicial DT'] = pd.to_datetime(df['Data Inicial'], format='%d/%m/%Y', errors='coerce')

        df_filtered = df.copy()
        if start_date:
            df_filtered = df_filtered[df_filtered['Data Final DT'] >= pd.to_datetime(start_date)]
        if end_date:
            df_filtered = df_filtered[df_filtered['Data Final DT'] <= pd.to_datetime(end_date)]
    else:
        df_filtered = pd.DataFrame(columns=[
            'Lucro (sats)', 'Taxas', 'Lucro Líquido (sats)', 'Rentabilidade (%)',
            'Data Final', 'Data Inicial', 'Lucro Acumulado'
        ])

    if df_filtered.empty:
        cards = html.Div(html.P("⚠️ Nenhuma ordem fechada encontrada no período selecionado.", style={"fontSize": "18px"}))
        graph = html.Div(html.P("📉 Nenhum dado disponível para gerar o gráfico.", style={"fontSize": "18px"}))
        table = html.P("📁 Nenhuma ordem fechada encontrada no período selecionado.", style={"fontSize": "18px"})
    else:
        total_orders = df_filtered.shape[0]
        total_gains = df_filtered[df_filtered['Lucro Líquido (sats)'] >= 0].shape[0]
        total_losses = df_filtered[df_filtered['Lucro Líquido (sats)'] < 0].shape[0]
        winrate = (total_gains / total_orders * 100) if total_orders else 0

        cards = html.Div([
            html.H4("📊 Resumo"),
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Lucro total (satoshis)", className="fs-5 fw-bold"),
                    dbc.CardBody(html.H4(f"{df_filtered['Lucro (sats)'].sum():,.0f}", className="fw-bold"))
                ], color="orange", inverse=True), width=3),
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Total de taxas (satoshis)", className="fs-5 fw-bold"),
                    dbc.CardBody(html.H4(f"{df_filtered['Taxas'].sum():,.0f}", className="fw-bold"))
                ], color="secondary", inverse=True), width=3),
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Lucro líquido (satoshis)", className="fs-5 fw-bold"),
                    dbc.CardBody(html.H4(f"{df_filtered['Lucro Líquido (sats)'].sum():,.0f}", className="fw-bold"))
                ], color="orange", inverse=True), width=3),
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Rentabilidade média", className="fs-5 fw-bold"),
                    dbc.CardBody(html.H4(f"{df_filtered['Rentabilidade (%)'].mean():.2f}%", className="fw-bold"))
                ], color="info", inverse=True), width=3),
            ], className="mb-4"),
            html.Br(),
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Total de Ordens", className="fs-5 fw-bold"),
                    dbc.CardBody(html.H4(f"{total_orders}", className="fw-bold"))
                ], color="dark", inverse=True), width=3),
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Ganhos", className="fs-5 fw-bold"),
                    dbc.CardBody(html.H4(f"{total_gains}", className="fw-bold"))
                ], color="success", inverse=True), width=3),
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Perdas", className="fs-5 fw-bold"),
                    dbc.CardBody(html.H4(f"{total_losses}", className="fw-bold"))
                ], color="danger", inverse=True), width=3),
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Aproveitamento", className="fs-5 fw-bold"),
                    dbc.CardBody(html.H4(f"{winrate:.2f}%", className="fw-bold"))
                ], color="info", inverse=True), width=3),
            ], className="mb-4")
        ])

        df_graph = df_filtered.groupby('Data Final DT', as_index=False)['Lucro Acumulado'].max()
        full_range = pd.date_range(df_graph['Data Final DT'].min(), df_graph['Data Final DT'].max())
        df_graph = df_graph.set_index('Data Final DT').reindex(full_range).rename_axis('Data Final DT').fillna(method='ffill').reset_index()
        df_graph['Data Final'] = df_graph['Data Final DT'].dt.strftime('%d/%m')

        fig = px.line(df_graph, x="Data Final", y="Lucro Acumulado", markers=True)
        fig.update_traces(line_shape='spline', line=dict(color='#F29727'))
        fig.update_layout(
            xaxis=dict(color='#FFFFFF', showgrid=False),
            yaxis=dict(color='#FFFFFF', showticklabels=False, showgrid=False),
            plot_bgcolor=custom_theme['background'],
            paper_bgcolor=custom_theme['background'],
            font=dict(color='#FFFFFF'),
            margin=dict(l=40, r=40, t=30, b=40)
        )

        graph = html.Div([
            html.H4("📈 Lucro Acumulado ao Longo do Tempo"),
            dcc.Graph(figure=fig, config={"displayModeBar": False})
        ])

        df_filtered = df_filtered.drop(columns=['Data Final DT', 'Data Inicial DT'], errors='ignore')
        table = html.Div([
            html.H4("📁 Ordens Fechadas"),
            dash_table.DataTable(
                data=df_filtered.to_dict('records'),
                columns=[{"name": i, "id": i} for i in df_filtered.columns],
                style_table={'overflowX': 'auto'},
                style_cell={'backgroundColor': custom_theme['background'], 'color': custom_theme['font_color']},
                style_header={'backgroundColor': custom_theme['accent'], 'color': 'white', 'fontWeight': 'bold'},
                sort_action='native',
                filter_action='none'
            )
        ])

    if df_open.empty:
        df_open = pd.DataFrame(columns=df.columns)  # mesmas colunas da tabela de ordens fechadas

    if df_open.empty:
        open_table = html.P("📌 Nenhuma ordem aberta encontrada.", style={"fontSize": "18px"})
    else:
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


    return table, min_date, max_date, cards, open_table, graph


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)