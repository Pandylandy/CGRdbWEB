from dash_html_components import Div, H1, Hr, Button, Label
from dash_marvinjs import DashMarvinJS
from dash import Dash, dcc, html, Input, Output, State
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
    {'name': 'ID', 'id': 'ID'},
    {'name': 'Structure', 'id': 'Structure'},
    {'name': 'Tanimoto', 'id': 'Tanimoto'},
    {'name': 'Data', 'id': 'Data'}]

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
            children=[html.Div([html.Div(id="loading-output")])],
            type="dot", style={'font-size': '50px'}
        ),
        Div([
            html.Div(html.H3("Search results"), style={'textAlign': 'center'}),
            html.Div(id=f'results')], className='col-md-7')],
    className='row col-md-12')

# error_dialog = dcc.ConfirmDialog(
#     id='confirm-error',
#     message='Invalid structure. Reaction must be provided'
# )

app.title = 'USPTO Search'
app.layout = Div([H1("USPTO database search", style={'textAlign': 'center'}),
                  Hr(), row_io, Hr(), row_desc])

db = load_schema(DB_NAME, password=PASSWORD, user=USER_NAME, port=PORT, host=HOST, database=DB)
db.cgrdb_init_session()


@app.callback(Output('editor', 'upload'),
              [Input('editor', 'download'), Input('submit-smiles', 'n_clicks')],
              State('smiles', 'value'))
def standardize(value, s_click, smi):
    s = None
    if s_click is None and not value and not smi:
        return ''
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
            return ''
        if isinstance(s, ReactionContainer):
            s = RDTool().transform([s]).loc[0, 'reaction']

        with StringIO() as f:
            with MRVWrite(f) as o:
                o.write(s)
            value = f.getvalue()
        return value


@app.callback([Output('results', 'children'), Output('smiles', 'value'), Output("loading-output", "children"),
               ],
              [Input('editor', 'upload')],
              [State('editor', 'upload'), State('smiles', 'value'), State('radio', 'value')])
def predict(n_clicks, structure_mrv, structure_smi, radio):
    structure = None
    if not n_clicks:
        return dash_table.DataTable(
            columns=columns,
            markdown_options={"html": True},
            fill_width=True,
            style_data={
                'whiteSpace': 'normal',
                'height': 'auto',
            },
            style_header={
                'whiteSpace': 'normal',
                'height': 'auto',
            }), '', ''

    elif structure_mrv:
        with BytesIO(structure_mrv.encode()) as f, MRVRead(f) as i:
            structure = next(i)
    if structure_smi:
        structure = smiles(structure_smi)
    if structure:
        try:
            df = prediction(structure, radio)
            if df is None:
                return dbc.Alert("No structures found :(", color="secondary"), '', ''
        except:
            print(format_exc())
            return dbc.Alert('Something went wrong. Please, check the query and try again', color='danger'), '', ''

        return html.Div(
            [
                dash_table.DataTable(
                    data=df.to_dict('records'),
                    columns=[
                        {"id": i, "name": i, "presentation": "markdown"} for i in df.columns
                    ],
                    page_current=0,
                    page_size=10,
                    page_action='custom',
                    markdown_options={"html": True},
                    fill_width=True,
                    style_cell_conditional=[
                        {'if': {'column_id': 'confidence', },
                         'display': 'None', },
                    ],
                    style_data={
                        'whiteSpace': 'normal',
                        'height': 'auto',
                    },
                    style_header={
                        'whiteSpace': 'normal',
                        'height': 'auto',
                    },
                )
            ],
        ), '', ''



def structure_to_html(structure):
    structure.clean2d()
    svg = structure.depict()
    b64 = base64.b64encode(svg.encode('utf-8')).decode("utf-8")
    html = f"<img src='data:image/svg+xml;base64,{b64}' width='350px' height='150px'>"
    return html


@db_session
def prediction(structure, search_type):
    structures, table = 'molecules', 'Molecule'
    f = None

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


if __name__ == '__main__':
    app.run_server(host='0.0.0.0', debug=True)
