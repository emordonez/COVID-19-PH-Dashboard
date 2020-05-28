from datetime import date, datetime

import pandas as pd

import plotly.express as px
import plotly.graph_objects as go

import dash
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
import dash_table

from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate


def case_aggregates(df):
    aggs = {
        'Cases': df['CaseCode'].count(),
        'Deaths': df[df['HealthStatus'] == 'Died']['CaseCode'].count(),
        'Recoveries': df[df['HealthStatus'] == 'Recovered']['CaseCode'].count()
    }
    return pd.Series(aggs)

def clean_dates(df):
    if df['HealthStatus'] == 'Died' and not pd.isna(df['DateDied']):
        df['DateRepRem'] = df['DateDied']
    elif df['HealthStatus'] == 'Recovered' and not pd.isna(df['DateRecover']):
        df['DateRepRem'] = df['DateRecover']
    return df['DateRepRem']


# Names management
reg_df = pd.read_csv('assets/names/regions.csv').set_index('internal_name')
regions_dict = reg_df.to_dict('index')
region_names = reg_df.index.tolist()

prov_df = pd.read_csv('assets/names/provinces.csv')
provinces_by_region_dict = prov_df.groupby('reg_internal')['prov_internal'].apply(list).to_dict()
province_names = dict(zip(prov_df['prov_internal'], prov_df['prov_name']))

# Case information cleaning
cases = pd.read_csv('DOH COVID Data Drop_ 20200524 - 04 Case Information.csv')
cases.drop(
    columns=[
        'Age', 'RemovalType', 'Admitted', 'CityMuniPSGC',
        'Quarantined', 'DateOnset', 'Pregnanttab'
    ],
    axis=1,
    inplace=True
)
cases.rename(
    columns={
        'RegionRes': 'Region', 'ProvRes': 'Province'
    },
    inplace=True
)
for column in cases[['DateRepConf', 'DateRepRem', 'DateDied', 'DateRecover']]:
    cases[column] = cases[column].dropna().apply(lambda x: datetime.strptime(x, '%Y-%m-%d'))
cases['DateRepRem'] = cases.apply(clean_dates, axis=1)
cases = cases.assign(Country='Philippines')

# Testing aggregates cleaning
aggs = pd.read_csv('DOH COVID Data Drop_20200524 - 07 Testing Aggregates.csv')

# Case and testing summary strings
CASES = f"{cases['CaseCode'].count():,}" + " cases"
DEATHS = f"{cases[cases['HealthStatus'] == 'Died']['CaseCode'].count():,}" + " deaths"
RECOVERIES = f"{cases[cases['HealthStatus'] == 'Recovered']['CaseCode'].count():,}" + " recoveries"
CONFIRM_TO_DATE = "confirmed by the Department of Health as of " + date.today().strftime("%B %d") + "."

TOTAL_TESTS = (f"{aggs.groupby('facility_name')['cumulative_unique_individuals'].max().sum():,}" +
    " people tested")
TEST_TO_DATE = "by 35 facilities nationwide, certified by the Department of Health."

# Inputs
all_provinces_check = dbc.FormGroup([
    dbc.Checklist(
        options=[{'label': 'Displaying aggregate national data', 'value': 'Yes'}],
        value=['Yes'],
        id='all-provinces-check'
    )
])
subdivisions_dropdown = dbc.FormGroup([
    dbc.Label('Filter provinces by region:'),
    dcc.Dropdown(
        id='regions-dropdown',
        options= [
            {'label': regions_dict[region]['shortened'],
            'value': region}
            for region in region_names
        ],
        multi=True,
        value=[],
        placeholder='Region'
    ),
    dcc.Dropdown(
        id='provinces-dropdown',
        multi=True,
        value=[],
        placeholder='Search provinces'
    ),
])
filters_switch = dbc.FormGroup([
    dbc.Label('Breakdown cases by:'),
    dbc.Checklist(
        options=[
            {'label': 'Age', 'value': 'AgeGroup'},
            {'label': 'Sex', 'value': 'Sex'},
            {'label': 'Health status', 'value': 'HealthStatus'},
        ],
        value=[],
        id='filters-switch-input',
        inline=True,
        switch=True
    )
])
search_panel = dbc.Collapse(
    dbc.Card(
        dbc.CardBody([
            all_provinces_check,
            subdivisions_dropdown,
            dbc.Button(
                'Select provinces',
                id='select-button',
                disabled=False,
                className='mb-1',
                color='primary',
                size='sm'
            ),
            filters_switch
        ])
    ),
    id='search-collapse'
)

# Outputs
summary_display = dbc.Jumbotron(
    dbc.Container(
        [
            html.H4(", ".join([CASES, DEATHS, RECOVERIES]), className='display-4'),
            html.P(CONFIRM_TO_DATE, className='lead'),
            html.Hr(className='my-4'),
            html.H4(TOTAL_TESTS, className='display-4'),
            html.P(TEST_TO_DATE, className='lead')
        ],
        fluid=True
    ),
    fluid=True
)
cases_display = [
    dbc.Row([
        html.Div(
            dcc.Graph(
                id='daily-cases-graph',
                config={'autosizable': True},
                animate=False
            ),
            style={'width': '49%', 'display': 'inline-block'}
        ),
        html.Div(
            dcc.Graph(
                id='total-cases-graph',
                config={'autosizable': True},
                animate=False
            ),
            style={'width': '49%', 'display': 'inline-block'}
        )
    ]),
    dbc.Row(
        dbc.Col(
            dash_table.DataTable(
                id='output-table',
                sort_action='native',
                style_as_list_view=True,
                style_cell={'padding': '5px'},
                style_header={
                    'backgroundColor': 'white',
                    'fontWeight': 'bold'
                },
                style_cell_conditional=[
                    {
                        'if': {'column_id': c},
                        'textAlign': 'left'
                    }
                    for c in ['Region', 'Province']
                ]
            )
        )
    )
]
testing_display = dbc.Row(dbc.Col(html.H4('Coming soon!')))

# App
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
server = app.server
app.config.suppress_callback_exceptions = True
app.layout = dbc.Container(
    [
        html.Div(
            [
                dcc.Store(id='regions-store'),
                dcc.Store(id='provinces-store'),
                dcc.Store(id='search-store')
            ],
            style={'display': 'none'}
        ),
        dbc.Row(html.H2('COVID-19 Cases and Testing in the Philippines'), className='mt-3 ml-1'),
        html.Hr(),
        dbc.Row([
            dbc.Col(
                dbc.Tabs(
                    [
                        dbc.Tab(label='Summary', tab_id='summary'),
                        dbc.Tab(label='Cases', tab_id='cases'),
                        dbc.Tab(label='Testing', tab_id='testing')
                    ],
                    id='tabs',
                    active_tab='summary'
                ),
                width="auto"
            ),
            dbc.Col(
                dbc.ButtonGroup([
                    dbc.Button(
                        'Filter cases',
                        id='collapse-button',
                        className='mb-3',
                        color='primary'
                    ), 
                    dbc.Button(
                        'About',
                        id='about-button',
                        className='mb-3',
                        color='info'
                    ),
                ]),
                width="auto"
            ),
            dbc.Modal(
                [
                    dbc.ModalHeader('About'),
                    dbc.ModalBody(dcc.Markdown('''
                    This dashboard tracks and visualizes the reported numbers of COVID-19
                    tests and cases in the Philippines.
                    * Data are sourced from the Philippine Department of Health's
                    [official COVID-19 data drops.](https://www.doh.gov.ph/2019-nCoV)
                    Archives are updated daily at 4 PM PHT.
                    * See the source on [Github](/).
                    ''')),
                    dbc.ModalFooter(
                        dbc.Button('Close', id='close-about', className='ml-auto')
                    )
                ],
                id='about-modal',
                size='lg'
            )
        ]),
        search_panel,
        html.Div(id='tab-content', className='p-4')
    ],
    fluid=True
)


@app.callback(
    Output('about-modal', 'is_open'),
    [Input('about-button', 'n_clicks'), Input('close-about', 'n_clicks')],
    [State('about-modal', 'is_open')]
)
def toggle_modal(n1, n2, is_open):
    if n1 or n2:
        return not is_open
    return is_open


@app.callback(
    Output('search-collapse', 'is_open'),
    [Input('collapse-button', 'n_clicks')],
    [State('search-collapse', 'is_open')]
)
def toggle_collapse(n, is_open):
    if n:
        return not is_open
    return is_open


@app.callback(
    [Output('regions-dropdown', 'disabled'),
        Output('provinces-dropdown', 'disabled'),
        Output('select-button', 'disabled')],
    [Input('all-provinces-check', 'value')]
)
def on_checkbox_change(checked):
    if checked:
        return True, True, True
    else:
        return False, False, False


@app.callback(
    [Output('regions-store', 'data'),
        Output('provinces-dropdown', 'options'),
        Output('provinces-dropdown', 'value'),
        Output('provinces-store', 'data')],
    [Input('regions-dropdown', 'value')]
)
def set_province_options(input_regions):
    if input_regions:
        output_options = [
            {'label': province_names[province], 'value': province}
            for region in input_regions
            for province in provinces_by_region_dict[region]
        ]
        output_value = [d['value'] for d in output_options]
        return input_regions, output_options, output_value, output_value
    else:
        return [], [], [], []


@app.callback(
    Output('search-store', 'data'),
    [Input('all-provinces-check', 'value'),
        Input('select-button', 'n_clicks'),
        Input('filters-switch-input', 'value')],
    [State('regions-store', 'data'),
        State('provinces-store', 'data')]
)
def filter_query(all_checked, n, filters, stored_regions, stored_provinces):
    df = cases
    if not all_checked and stored_regions and stored_provinces:
        df = df.query("Region in @stored_regions")
        bar_df = df.query("(Province in @stored_provinces) | (Province != Province)")
        line_df = bar_df
        bar_df = df.groupby(['Region', 'Province'] + filters).apply(case_aggregates)
    elif filters:
        bar_df = df.groupby(filters).apply(case_aggregates)
        line_df = df
    else:
        bar_df = df.groupby('Country').apply(case_aggregates)
        line_df = df
    bar_df.reset_index(inplace=True)
    line_df.reset_index()
    return {'bar': bar_df.to_dict('records'), 'line': line_df.to_dict('records')}


@app.callback(
    [Output('daily-cases-graph', 'figure'), Output('total-cases-graph', 'figure')],
    [Input('search-store', 'data')],
    [State('tabs', 'active_tab')]
)
def on_data_set_figures(data, active_tab):
    if data is None or len(data) == 0:
        raise PreventUpdate
    elif active_tab != 'cases':
        raise PreventUpdate
    
    df = pd.DataFrame.from_dict(data['line'])

    df = df.groupby('DateRepConf')['CaseCode'].count().reset_index(name='Cases')
    df = df.assign(Total = df['Cases'].cumsum())
    daily_fig = go.Figure()
    daily_fig.add_trace(go.Scatter(x=df['DateRepConf'], y=df['Cases'], mode='lines', name='Daily Cases'))
    total_fig = go.Figure()
    total_fig.add_trace(go.Scatter(x=df['DateRepConf'], y=df['Total'], mode='lines', name='Total Cases'))
    return daily_fig, total_fig


@app.callback(
    [Output('output-table', 'data'), Output('output-table', 'columns')],
    [Input('search-store', 'data')],
    [State('tabs', 'active_tab')]
)
def on_data_set_table(data, active_tab):
    df = pd.DataFrame.from_dict(data['bar'])
    columns = [{'name': i, 'id': i} for i in df.columns]
    return data['bar'], columns


@app.callback(
    Output('tab-content', 'children'),
    [Input('tabs', 'active_tab')]
)
def render_tab_content(active_tab):
    if active_tab is not None:
        if active_tab == 'summary':
            return summary_display
        elif active_tab == 'cases':
            return cases_display
        elif active_tab == 'testing':
            return testing_display


if __name__ == '__main__':
    app.run_server(host='127.0.0.1', port='8050', debug=True)
