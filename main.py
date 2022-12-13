from dash.html import Div, H1, H3, Hr, Button, Label
from dash_marvinjs import DashMarvinJS
from dash import Dash, dcc, Input, Output, State
from dash import dash_table

from CGRdb import load_schema
from CGRtools.containers import ReactionContainer
from CGRtools.files import MRVWrite, MRVRead
from CGRtools import smiles
from CIMtools.preprocessing import RDTool
from config import *
from io import BytesIO, StringIO
from os import environ
from pony.orm import db_session
from traceback import format_exc

import base64
import dash_bootstrap_components as dbc
import json
import pandas

external_stylesheets = [{'href': 'https://stackpath.bootstrapcdn.com/bootstrap/4.1.3/css/bootstrap.min.css',
                         'rel': 'stylesheet', 'crossorigin': 'anonymous',
                         'integrity': 'sha384-MCw98/SFnGE8fJT3GXwEOngsV7Zt27NXFoaoApmYm81iuXoPkFOJwJ8ERdknLPMO'},
                        'https://codepen.io/chriddyp/pen/bWLwgP.css']

external_scripts = [{'src': 'https//cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.4/MathJax.js?config=TeX-MML-AM_CHTML'}]
app = Dash(__name__, external_stylesheets=external_stylesheets, external_scripts=external_scripts, update_title=None)
server = app.server
server.secret_key = environ.get('SECRET_KEY', 'development')

desc = '''
__Instruction for database searching:__

* Insert SMILES of molecule/reaction and click __submit__ button *or* 
+ Draw a molecule/reaction and put the __Upload__ button in Marvin window *or* 
* __Choose__ the type of search
* You are breathtaking! Look at the results in the __results table__


'''
desc_3 = '''
__CGRdbWEB:__ You can use this application to search molecules and reactions by structure, substructure and similarity 
in USPTO database. For each query it will be returned Tanimoto similarity coefficient. All results in the output table 
is sorted by similarity to query.

Author: Adeliia Fatykhova adelia@cimm.site

'''
columns = [
    {'name': 'ID', 'id': 'ID', 'presentation': 'markdown'},
    {'name': 'Structure', 'id': 'Structure', 'presentation': 'markdown'},
    {'name': 'Tanimoto', 'id': 'Tanimoto', 'presentation': 'markdown'},
    {'name': 'Data', 'id': 'Data', 'presentation': 'markdown'}]

row_desc = Div(
    [Div([dcc.Markdown(desc)], className='col-md-5'),
     Div([dcc.Markdown(desc_3)], className='col-md-7')], className='row col-md-12')

row_io = Div(
    [Div(
        [Label(["Insert SMILES: ", dcc.Input(id='smiles', value='', type='text',
                                             style={"width": "70%"}),
                Button(id='submit-smiles', type='submit', children='Submit'),
                ], style={"width": "100%"}),
         Label(["Search type: ", dbc.RadioItems(
             id="radio",
             value='find_structure',
             labelClassName="button",
             inline=True,
             options=[
                 {'label': 'Exact ', 'value': 'find_structure'},
                 {'label': 'Substructure ', 'value': 'find_substructures'},
                 {'label': 'Similarity ', 'value': 'find_similar'}
             ],
             style={'width': '70%'},
         )], style={"width": "100%"}),
         Div(style={"height": "20px"}),

         DashMarvinJS(id='editor', marvin_url=app.get_asset_url('mjs/editor.html'),
                      marvin_width='100%'),
         ], className='col-md-5'),
        dcc.Loading(
            id="loading",
            children=[Div([Div(id="loading-output")])],
            type="dot", style={'font-size': '50px'}
        ),
        Div([
            Div(H3("Search results"), style={'textAlign': 'center'}),
            Div(id=f'results', style={'display': 'none'}),
            Div(id=f'none-result'),

            Div(children=[dash_table.DataTable(id='data-results', page_current=0,
                                               page_size=5,
                                               page_action='custom', columns=columns,
                                               markdown_options={"html": True},
                                               fill_width=True,
                                               style_data={
                                                   'whiteSpace': 'normal',
                                                   'height': 'auto',
                                               },
                                               style_header={
                                                   'whiteSpace': 'normal',
                                                   'height': 'auto',
                                               })])], className='col-md-7')],

    className='row col-md-12')

error_dialog = dcc.ConfirmDialog(
    id='confirm-error',
    message='Invalid structure. Check the query and try again'
)

app.title = 'USPTO Search'
app.layout = Div([H1("USPTO database search", style={'textAlign': 'center'}),
                  error_dialog, Hr(), row_io, Hr(), row_desc])

db = load_schema(DB_NAME, password=PASSWORD, user=USER_NAME, port=PORT, host=HOST, database=DB)
db.cgrdb_init_session()


@app.callback([Output('editor', 'upload'), Output('confirm-error', 'displayed')],
              [Input('editor', 'download'), Input('submit-smiles', 'n_clicks')],
              State('smiles', 'value'))
def standardize(value, s_click, smi):
    s = None
    if s_click is None and not value and not smi:
        return '', False
    if value:
        with BytesIO(value.encode()) as f, MRVRead(f) as i:
            s = next(i)
    if s_click is not None and smi:
        s = smiles(smi)
    if s is not None:
        try:
            s.canonicalize()
            s.thiele()
            s.clean2d()
        except:
            print(format_exc())
            return '', True
        if isinstance(s, ReactionContainer):
            s = RDTool().transform([s]).loc[0, 'reaction']

        with StringIO() as f:
            with MRVWrite(f) as o:
                o.write(s)
            value = f.getvalue()
        return value, False


@app.callback([Output('smiles', 'value'), Output("loading-output", "children"),
               Output('results', 'children'), Output('none-result', 'children')],
              [Input('editor', 'upload')],
              [State('editor', 'upload'), State('smiles', 'value'), State('radio', 'value')])
def predict(n_clicks, structure_mrv, structure_smi, radio):
    structure = None
    if not n_clicks:
        return '', '', '', ''

    elif structure_mrv and n_clicks:
        with BytesIO(structure_mrv.encode()) as f, MRVRead(f) as i:
            structure = next(i)
    if structure_smi:
        structure = smiles(structure_smi)
    if structure:
        try:
            df = search(structure, radio)
            if df is None:
                return '', '', '', dbc.Alert("No structures found :(", color="secondary")
        except:
            print(format_exc())
            return '', '', '', dbc.Alert('Something went wrong. Please, check the query and try again', color='danger')

        return '', '', json.dumps(df.to_json(orient="records")), ''


@app.callback(
    Output('data-results', 'data'),
    Output('data-results', 'page_count'),
    Output('data-results', 'style_table'),
    Input('data-results', "page_current"),
    Input('data-results', "page_size"),
    Input('results', 'children'))
def update_table(page_current, page_size, data):
    if data:
        data = json.loads(data)
        data = pandas.read_json(data, orient="records")
        print(int(data.shape[0] / page_size) + 1)
        return data.iloc[
               page_current * page_size:(page_current + 1) * page_size
               ].to_dict('records'), int(data.shape[0] / page_size) + 1, {}
    else:
        return [], 1, {'display': 'none'}


def structure_to_html(structure):
    structure.clean2d()
    svg = structure.depict()
    b64 = base64.b64encode(svg.encode('utf-8')).decode("utf-8")
    return f"<img src='data:image/svg+xml;base64,{b64}' width='300px' height='100px'>"


@db_session
def search(structure, search_type):
    structures, table = 'molecules', 'Molecule'
    if isinstance(structure, ReactionContainer):
        structures = 'reactions'
        table = 'Reaction'

    db.cgrdb_init_session()
    f = getattr(getattr(db, table), search_type)(structure)
    if f:
        if search_type == 'find_structure':
            tanimotos = (1.0,)
            f = [f]
        else:
            tanimotos = f.tanimotos()
            f = getattr(f, structures)()
    if f is None:
        df = None
    else:
        data = []
        for s in f:
            res = []
            for d in s.metadata:
                res.append(d.data['text'])
            data.append(res)

        df = pandas.DataFrame({
            'ID': [s.id for s in f],
            'Structure': [structure_to_html(s.structure) for s in f],
            'Tanimoto': (round(t, 2) for t in tanimotos),
            # 'Data': [y.data for x in f for y in x.metadata]
            'Data': ';\n'.join(str(y) for x in data for y in x)
        })
    return df


def formatted(data):
    style = {'columns': columns,
             'markdown_options': {"html": True},
             'fill_width': True,
             'style_data': {
                 'whiteSpace': 'normal',
                 'height': 'auto',
             },
             'style_header': {
                 'whiteSpace': 'normal',
                 'height': 'auto',
             }}
    if len(data):
        return dash_table.DataTable(**style,
                                    id='data-results',
                                    data=data.to_dict('records'),
                                    page_current=0,
                                    page_size=10,
                                    page_action='custom'
                                    )
    else:
        return []


if __name__ == '__main__':
    app.run_server(host='0.0.0.0', debug=True)
