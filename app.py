from datetime import date, datetime

import dash
import dash_bootstrap_components as dbc
import dash_core_components as dcc
import dash_html_components as html
import dash_table
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

import pandas as pd

import plotly.express as px


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


# Read data
# TODO Write scripts to automatically download the latest data from Google Drive
cases = pd.read_csv('DOH COVID Data Drop_ 20200617 - 04 Case Information.csv')
aggs = pd.read_csv('DOH COVID Data Drop_ 20200617 - 07 Testing Aggregates.csv')

# Names management
reg_df = pd.read_csv('assets/regions.csv').set_index('internal_name')
regions_dict = reg_df.to_dict('index')
region_names = reg_df.index.tolist()

prov_df = pd.read_csv('assets/provinces.csv')
provinces_by_region_dict = prov_df.groupby('reg_internal')['prov_internal'].apply(list).to_dict()
province_names = dict(zip(prov_df['prov_internal'], prov_df['prov_name']))

# Case information cleaning
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
cases = cases.assign(Country='PHILIPPINES')
AGEGROUP_ORDER = [
    '0 to 4', '5 to 9', '10 to 14', '15 to 19', '20 to 24', '25 to 29',
    '30 to 34','35 to 39','40 to 44', '45 to 49', '50 to 54', '55 to 59',
    '60 to 64', '65 to 69', '70 to 74', '75 to 79', '80+'
]

# Populations for rate adjustment
population = pd.read_csv('assets/population.csv')
cases = cases.merge(population, left_on='Province', right_on='name', how='left')
NATIONAL_POP = population[population['name'] == 'PHILIPPINES']['pop_2015'].iloc[0]

# Default data for display
# Same code as filter_query(), but callback functions can't be called outside the wrapper's scope
table_df = cases.query("`Province` == 'METRO MANILA'")
df = table_df
table_df = table_df.groupby('Province').apply(case_aggregates)
table_df.reset_index(inplace=True)
df.reset_index()

cases_df = df.groupby(
    ['DateRepConf', 'Province', 'pop_2015']
)['CaseCode'].count().reset_index(name='Cases')

dates = cases_df['DateRepConf'].sort_values().values
start_date = dates[0]
end_date = dates[-1]
datelist = pd.DataFrame(pd.date_range(start=start_date, end=end_date, name='Date'))  
cases_df = datelist.merge(
    cases_df, left_on='Date', right_on='DateRepConf', how='left')

cases_df['Cases'] = cases_df['Cases'].fillna(0)
cases_df['Total'] = cases_df.groupby('Province')['Cases'].cumsum()
cases_df['Per100k'] = cases_df['Total'] / cases_df['pop_2015'] * 100000
cases_df.drop(columns=['DateRepConf', 'pop_2015'], inplace=True)    
cases_df = cases_df.dropna()

deaths = df.query("`HealthStatus` == 'Died'")
totals = df.groupby('Province')['CaseCode'].count().reset_index(name='Cases')
deaths = deaths.groupby('Province')['CaseCode'].count().reset_index(name='Deaths')
rates_df = totals.merge(deaths, on='Province')
rates_df['Rate'] = rates_df['Deaths'] / rates_df['Cases']

default_data = {
    'cases': cases_df.to_dict('records'),
    'deaths': rates_df.to_dict('records'),
    'aggs': table_df.to_dict('records')
}

# Testing aggregates cleaning
# TODO Clean and display data in aggs dataframe

# Case and testing summary strings
# TODO Format confirmation string to show date of the latest data drop
CASES = f"{cases['CaseCode'].count():,}" + " cases"
DEATHS = f"{cases[cases['HealthStatus'] == 'Died']['CaseCode'].count():,}" + " deaths"
RECOVERIES = f"{cases[cases['HealthStatus'] == 'Recovered']['CaseCode'].count():,}" + " recoveries"
CONFIRM_TO_DATE = "confirmed by the Department of Health as of Jun 17." # + date.today().strftime("%B %d") + "."

TOTAL_TESTS = (f"{aggs.groupby('facility_name')['cumulative_unique_individuals'].max().sum():,}" +
    " people tested")
TEST_TO_DATE = "by 35 DOH certified facilities nationwide."

# Inputs
all_provinces_check = dbc.FormGroup([
    dbc.Checklist(
        options=[{'label': 'Display aggregate national data', 'value': 'Y'}],
        value=[],
        id='all-provinces-check'
    )
])
summed_provinces_check = dbc.FormGroup([
    dbc.Checklist(
        options=[{'label': 'Group provincial data together', 'value': 'Y'}],
        value=[],
        id='summed-provinces-check'
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
        value=['NCR'],
        placeholder='Region'
    ),
    dcc.Dropdown(
        id='provinces-dropdown',
        multi=True,
        value=['METRO MANILA'],
        placeholder='Search provinces'
    ),
    dbc.Button(
        'Select provinces',
        id='select-button',
        n_clicks=0,
        disabled=False,
        className='mt-3 mb-1',
        color='primary',
        size='sm'
    )
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
            summed_provinces_check,
            subdivisions_dropdown,
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
    dbc.Row(
        dbc.Col(
            dcc.Loading(
                dcc.Graph(
                    id='cases-graph',
                    config={'autosizable': True},
                    animate=False,
                    figure={}
                ),
                type='circle'
            )
        )
    ),
    dbc.Row(
        dbc.Col(
            dcc.Loading(
                dcc.Graph(
                    id='deaths-graph',
                    config={'autosizable': True},
                    animate=False,
                    figure={}
                ),
                type='circle'
            )
        )
    ),
    dbc.Row(
        dbc.Col(
            dash_table.DataTable(
                id='output-table',
                sort_action='native',
                style_cell={'padding': '5px'},
                style_header={
                    'backgroundColor': 'rgb(230, 230, 230)',
                    'fontWeight': 'bold'
                },
                style_cell_conditional=[
                    {
                        'if': {'column_id': c},
                        'textAlign': 'left'
                    }
                    for c in ['Country', 'Region', 'Province']
                ],
                style_data_conditional=[
                    {
                        'if': {'row_index': 'odd'},
                        'backgroundColor': 'rgb(248, 248, 248)'
                    }
                ]
            )
        )
    )
]
# TODO Graphs for testing aggregates
testing_display = dbc.Row(dbc.Col(html.H4('Coming soon!')))

# App
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
server = app.server
app.config.suppress_callback_exceptions = True
app.layout = dbc.Container(
    [
        html.Div(
            [
                dcc.Store(id='regions-store', data=[]),
                dcc.Store(id='options-store', data=[]),
                dcc.Store(id='provinces-store', data=[]),
                dcc.Store(id='search-store', data=default_data)
            ],
            style={'display': 'none'}
        ),
        dbc.Row(html.H2('COVID-19 Cases and Testing in the Philippines'), className='mt-3 ml-1'),
        html.Hr(),
        dbc.Row(
            dbc.Col(
                dbc.Collapse(
                    html.P(
                    '''
                    Hover on a trace for more data. Click on a trace in the legend to
                    add/remove it from the plot. Double click on a trace to isolate it,
                    and double click again to restore all other traces. Use the tools in
                    the upper right of the plot to pan, zoom, and compare data on hover.
                    '''
                    ),
                    id='instructions-collapse',
                    is_open=False
                )
            )
        ),
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
                    This dashboard tracks and analyzes the reported numbers of COVID-19
                    cases in the Philippines. Break down the pandemic at the
                    national and provincial levels and by patients' age, sex, and
                    the severity/outcome of their case.
                    * Data are sourced from the Philippine Department of Health's
                    [official COVID-19 data drops.](https://www.doh.gov.ph/2019-nCoV)
                    Archives are updated daily at 4 PM PHT.
                    * Rates are adjusted for the 2015 census population.
                    * See this app's repository on
                    [Github.](https://github.com/emordonez/COVID-19-PH-Dashboard)
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
        Output('provinces-dropdown', 'value')],
    [Input('regions-dropdown', 'value')],
    [State('regions-store', 'data'), 
        State('options-store', 'data'),
        State('provinces-store', 'data')]
)
def set_province_options(input_regions, stored_regions, stored_options, stored_provinces): 
    if input_regions:
        if len(input_regions) == len(stored_regions) + 1:
            (new_region, ) = set(input_regions) - set(stored_regions)
            new_provinces = provinces_by_region_dict[new_region]
            new_options = [
                {'label': province_names[province], 'value': province}
                for province in new_provinces
            ]
            output_options = stored_options + new_options
            output_value = stored_provinces + [d['value'] for d in new_options]
        elif len(input_regions) == len(stored_regions) - 1:
            (removed_region, ) = set(stored_regions) - set(input_regions)
            removed_provinces = provinces_by_region_dict[removed_region]
            output_options = [
                {'label': province_names[province], 'value': province}
                for region in input_regions
                for province in provinces_by_region_dict[region]
            ]
            output_value = [
                province for province in stored_provinces
                if province not in removed_provinces
            ]
        return input_regions, output_options, output_value
    else:
        return [], [], []


@app.callback(
    [Output('options-store', 'data'), Output('provinces-store', 'data')],
    [Input('provinces-dropdown', 'options'), Input('provinces-dropdown', 'value')]
)
def store_provinces(options, value):
    return options, value


@app.callback(
    Output('search-store', 'data'),
    [Input('all-provinces-check', 'value'),
        Input('select-button', 'n_clicks'),
        Input('filters-switch-input', 'value'),
        Input('tabs', 'active_tab')],
    [State('regions-store', 'data'),
        State('provinces-store', 'data'),
        State('summed-provinces-check', 'value')]
)
def filter_query(
    all_checked, n, filters, active_tab,
    input_regions, input_provinces, summed_check):
    if active_tab != 'cases':
        raise PreventUpdate

    # Filter cases for input provinces and filters
    if not all_checked and input_regions and input_provinces:
        table_df = cases.query("Region in @input_regions").query("Province in @input_provinces")
        if summed_check:
            table_df['Province'] = "{} PROVINCES".format(len(input_provinces))
            table_df['pop_2015'] = table_df['pop_2015'].unique().sum()
        line_df = table_df
        table_df = table_df.groupby(['Province'] + filters).apply(case_aggregates)
    elif filters:
        line_df = cases
        table_df = cases.groupby(filters).apply(case_aggregates)
    else:
        line_df = cases
        table_df = cases.groupby('Country').apply(case_aggregates)
    table_df.reset_index(inplace=True)
    line_df.reset_index()

    # Clean cases data
    filters = [x for x in filters if x != 'HealthStatus']
    if all_checked:
        cases_df = line_df.groupby(
            ['DateRepConf', 'Country'] + filters
        )['CaseCode'].count().reset_index(name='Cases')
    else:
        cases_df = line_df.groupby(
            ['DateRepConf', 'Province', 'pop_2015'] + filters
        )['CaseCode'].count().reset_index(name='Cases')

    dates = cases_df['DateRepConf'].sort_values().values
    start_date = dates[0]
    end_date = dates[-1]
    datelist = pd.DataFrame(pd.date_range(start=start_date, end=end_date, name='Date'))  
    cases_df = datelist.merge(
        cases_df, left_on='Date', right_on='DateRepConf', how='left')

    cases_df['Cases'] = cases_df['Cases'].fillna(0)
    if all_checked:
        cases_df['Total'] = cases_df.groupby(['Country'] + filters)['Cases'].cumsum()
        cases_df['Per100k'] = cases_df['Total'] / NATIONAL_POP * 100000
        cases_df.drop(columns=['DateRepConf'], inplace=True)   
    else:
        cases_df['Total'] = cases_df.groupby(['Province'] + filters)['Cases'].cumsum()
        cases_df['Per100k'] = cases_df['Total'] / cases_df['pop_2015'] * 100000
        cases_df.drop(columns=['DateRepConf', 'pop_2015'], inplace=True)    
    cases_df = cases_df.dropna()
    
    # Clean deaths data
    deaths = line_df.query("`HealthStatus` == 'Died'")
    if all_checked:
        totals = line_df.groupby(
            ['Country'] + filters
        )['CaseCode'].count().reset_index(name='Cases')
        deaths = deaths.groupby(
            ['Country'] + filters
        )['CaseCode'].count().reset_index(name='Deaths')
        rates_df = totals.merge(deaths, on=(['Country'] + filters))
    else:
        totals = line_df.groupby(
            ['Province'] + filters
        )['CaseCode'].count().reset_index(name='Cases')
        deaths = deaths.groupby(
            ['Province'] + filters
        )['CaseCode'].count().reset_index(name='Deaths')
        rates_df = totals.merge(deaths, on=(['Province'] + filters))
    rates_df['Rate'] = rates_df['Deaths'] / rates_df['Cases']

    data = {
        'cases': cases_df.to_dict('records'),
        'deaths': rates_df.to_dict('records'),
        'aggs': table_df.to_dict('records')
    }
    return data


@app.callback(
    [Output('cases-graph', 'figure'), Output('deaths-graph', 'figure')],
    [Input('search-store', 'data')],
    [State('all-provinces-check', 'value'), 
        State('filters-switch-input', 'value'),
        State('tabs', 'active_tab')]
)
def on_data_set_figures(data, all_checked, filters, active_tab):    
    if data is None or len(data) == 0:
        raise PreventUpdate

    cases_df = pd.DataFrame.from_dict(data['cases'])
    deaths_df = pd.DataFrame.from_dict(data['deaths'])

    if all_checked:
        if 'AgeGroup' in filters and 'Sex' in filters:
            cases_fig = px.line(
                cases_df,
                x='Date',
                y='Total',
                color='AgeGroup',
                facet_col='Sex',
                hover_data=['Cases', 'Total'],
                category_orders={'AgeGroup': AGEGROUP_ORDER},
                title='COVID-19 cases nationwide by sex and age groups',
                template='plotly'
            )
            deaths_fig = px.scatter(
                deaths_df,
                x='Cases',
                y='Rate',
                size='Deaths',
                color='AgeGroup',
                facet_col='Sex',
                hover_data=['Deaths'],
                category_orders={'AgeGroup': AGEGROUP_ORDER, 'Sex': ['Male', 'Female']},
                log_x=True,
                title='COVID-19 deaths nationwide by sex and age groups',
                template='plotly'
            )
        elif 'AgeGroup' in filters:
            cases_fig = px.line(
                cases_df,
                x='Date',
                y='Total',
                color='AgeGroup',
                hover_data=['Cases', 'Total'],
                category_orders={'AgeGroup': AGEGROUP_ORDER},
                title='COVID-19 cases nationwide by age groups',
                template='plotly'
            )
            deaths_fig = px.scatter(
                deaths_df,
                x='Cases',
                y='Rate',
                size='Deaths',
                color='AgeGroup',
                hover_data=['Deaths'],
                category_orders={'AgeGroup': AGEGROUP_ORDER},
                log_x=True,
                title='COVID-19 deaths nationwide by age groups',
                template='plotly'
            )
        elif 'Sex' in filters:
            cases_fig = px.line(
                cases_df,
                x='Date',
                y='Total',
                color='Sex',
                hover_data=['Cases', 'Total'],
                category_orders={'Sex': ['Male', 'Female']},
                title='COVID-19 cases nationwide by sex',
                template='plotly'
            )
            deaths_fig = px.scatter(
                deaths_df,
                x='Cases',
                y='Rate',
                size='Deaths',
                color='Sex',
                hover_data=['Deaths'],
                category_orders={'Sex': ['Male', 'Female']},
                log_x=True,
                title='COVID-19 deaths nationwide by sex',
                template='plotly'
            )
        else:
            cases_fig = px.line(
                cases_df,
                x='Date',
                y='Per100k',
                color='Country',
                hover_data=['Cases', 'Total'],
                title='COVID-19 case rates nationwide',
                template='plotly'
            )
            deaths_fig = px.scatter(
                deaths_df,
                x='Cases',
                y='Rate',
                size='Deaths',
                color='Country',
                hover_data=['Deaths'],
                log_x=True,
                title='COVID-19 deaths nationwide',
                template='plotly'
            )
    else:
        if 'AgeGroup' in filters and 'Sex' in filters:
            cases_fig = px.line(
                cases_df,
                x='Date',
                y='Total',
                line_group='Province',
                color='AgeGroup',
                facet_col='Sex',
                hover_data=['Cases', 'Total'],
                category_orders={'AgeGroup': AGEGROUP_ORDER, 'Sex': ['Male', 'Female']},
                title='Provincial COVID-19 cases by sex and age groups',
                template='plotly'
            )
            deaths_fig = px.scatter(
                deaths_df,
                x='Cases',
                y='Rate',
                size='Deaths',
                color='AgeGroup',
                facet_col='Sex',
                hover_data=['Province', 'Deaths'],
                category_orders={'AgeGroup': AGEGROUP_ORDER, 'Sex': ['Male', 'Female']},
                log_x=True,
                title='Provincial COVID-19 deaths by sex and age groups',
                template='plotly'
            )
        elif 'AgeGroup' in filters:
            cases_fig = px.line(
                cases_df,
                x='Date',
                y='Total',
                line_group='Province',
                color='AgeGroup',
                hover_data=['Cases', 'Total'],
                category_orders={'AgeGroup': AGEGROUP_ORDER},
                title='Provincial COVID-19 cases by age groups',
                template='plotly'
            )
            deaths_fig = px.scatter(
                deaths_df,
                x='Cases',
                y='Rate',
                size='Deaths',
                color='AgeGroup',
                hover_data=['Province', 'Deaths'],
                category_orders={'AgeGroup': AGEGROUP_ORDER},
                log_x=True,
                title='Provincial COVID-19 deaths by age groups',
                template='plotly'
            )
        elif 'Sex' in filters:
            cases_fig = px.line(
                cases_df,
                x='Date',
                y='Total',
                line_group='Province',
                color='Sex',
                hover_data=['Cases', 'Total'],
                category_orders={'Sex': ['Male', 'Female']},
                title='Provincial COVID-19 cases by sex',
                template='plotly'
            )
            deaths_fig = px.scatter(
                deaths_df,
                x='Cases',
                y='Rate',
                size='Deaths',
                color='Province',
                facet_col='Sex',
                hover_data=['Deaths'],
                category_orders={'Sex': ['Male', 'Female']},
                log_x=True,
                title='Provincial COVID-19 deaths by sex',
                template='plotly'
            )
        else:
            cases_fig = px.line(
                cases_df,
                x='Date',
                y='Per100k',
                color='Province',
                hover_data=['Cases', 'Total'],
                title='Provincial COVID-19 cases',
                template='plotly'
            )
            deaths_fig = px.scatter(
                deaths_df,
                x='Cases',
                y='Rate',
                size='Deaths',
                color='Province',
                hover_data=['Deaths'],
                log_x=True,
                title='Provincial COVID-19 deaths',
                template='plotly'
            )
    return cases_fig, deaths_fig


@app.callback(
    [Output('output-table', 'columns'), Output('output-table', 'data')],
    [Input('search-store', 'data')],
    [State('tabs', 'active_tab')]
)
def on_data_set_table(data, active_tab):
    if data is None or len(data) == 0:
        raise PreventUpdate
    elif active_tab != 'cases':
        raise PreventUpdate

    df = pd.DataFrame.from_dict(data['aggs'])
    columns = [{'name': i, 'id': i} for i in df.columns]
    return columns, data['aggs']


@app.callback(
    [Output('tab-content', 'children'), Output('instructions-collapse', 'is_open')],
    [Input('tabs', 'active_tab')],
)
def render_tab_content(active_tab):
    if active_tab is not None:
        if active_tab == 'summary':
            return summary_display, False
        elif active_tab == 'cases':
            return cases_display, True
        elif active_tab == 'testing':
            return testing_display, False


if __name__ == '__main__':
    app.run_server(debug=True)
