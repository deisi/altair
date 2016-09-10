"""Altair Directive for sphinx"""

import ast
import os
import json

import jinja2

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.parsers.rst.directives import flag, unchanged

from sphinx.locale import _
from sphinx import addnodes, directives
from sphinx.util.nodes import set_source_info

from .utils import exec_then_eval

try:
    import altair
    from altair.api import TopLevelMixin
except ImportError:
    altair = None


# TODO: can we put these script tags in the document header?

VGL_TEMPLATE = jinja2.Template("""
<div id="{{ div_id }}">
<script src="https://d3js.org/d3.v3.min.js"></script>
<script src="https://vega.github.io/vega/vega.js"></script>
<script src="https://vega.github.io/vega-lite/vega-lite.js"></script>
<script src="https://vega.github.io/vega-editor/vendor/vega-embed.js" charset="utf-8"></script>
<script>
  vg.embed("#{{ div_id }}", "{{ filename }}", function(error, result) {});
</script>
</div>
""")


class altair_plot(nodes.General, nodes.Element):
    pass


class AltairPlotSetupDirective(Directive):
    has_content = True

    def run(self):
        env = self.state.document.settings.env

        targetid = "altair-plot-{0}".format(env.new_serialno('altair-plot'))
        targetnode = nodes.target('', '', ids=[targetid])

        code = '\n'.join(self.content)

        if not hasattr(env, 'altair_plot_setup'):
            env.altair_plot_setup = []
        env.altair_plot_setup.append({
            'docname': env.docname,
            'lineno': self.lineno,
            'code': code,
            'target': targetnode,
        })

        return [targetnode]


def purge_altair_plot_setup(app, env, docname):
    if not hasattr(env, 'altair_plot_setup'):
        return
    env.altair_plot_setup = [item for item in env.altair_plot_setup
                             if item['docname'] != docname]


class AltairPlotDirective(Directive):

    has_content = True

    option_spec = {'hide-code': flag,
                   'code-below': flag,
                   'alt': unchanged}

    def run(self):
        env = self.state.document.settings.env
        app = env.app

        show_code = 'hide-code' not in self.options
        code_below = 'code-below' in self.options

        setupcode = '\n'.join(item['code']
                              for item in getattr(env, 'altair_plot_setup', [])
                              if item['docname'] == env.docname)
        code = '\n'.join(self.content)

        if show_code:
            source_literal = nodes.literal_block(code, code)
            source_literal['language'] = 'python'

        #get the name of the source file we are currently processing
        rst_source = self.state_machine.document['source']
        rst_dir = os.path.dirname(rst_source)
        rst_filename = os.path.basename(rst_source)

        # use the source file name to construct a friendly target_id
        serialno = env.new_serialno('altair-plot')
        rst_base = rst_filename.replace('.', '-')
        div_id = "{0}-altair-plot-{1}".format(rst_base, serialno)
        target_id = "{0}-altair-source-{1}".format(rst_base, serialno)
        target_node = nodes.target('', '', ids=[target_id])

        # create the node in which the plot will appear;
        # this will be processed by html_visit_altair_plot
        plot_node = altair_plot()
        plot_node['target_id'] = target_id
        plot_node['div_id'] = div_id
        plot_node['code'] = code
        plot_node['setupcode'] = setupcode
        plot_node['relpath'] = os.path.relpath(rst_dir, env.srcdir)
        plot_node['rst_source'] = rst_source
        plot_node['rst_lineno'] = self.lineno

        if 'alt' in self.options:
            plot_node['alt'] = self.options['alt']

        result = [target_node]

        if code_below:
            result += [plot_node]
        if show_code:
            result += [source_literal]
        if not code_below:
            result += [plot_node]

        return result


def html_visit_altair_plot(self, node):
    # Execute the setup code, saving the global & local state
    _globals, _locals = {}, {}
    if node['setupcode']:
        exec(node['setupcode'], _globals, _locals)

    # Execute the plot code in this context, evaluating the last line
    chart = exec_then_eval(node['code'], _globals, _locals)

    # Last line should be a chart; convert to spec dict
    spec = chart.to_dict()

    # Create the vega-lite spec to embed
    embed_spec = json.dumps({'mode': 'vega-lite',
                             'actions': {'editor': True,
                                         'source': False,
                                         'export': True},
                             'spec': spec})

    # Write embed_spec to a *.vl.json file
    dest_dir = os.path.join(self.builder.outdir, node['relpath'])
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    filename = "{0}.vl.json".format(node['div_id'])
    dest_path = os.path.join(dest_dir, filename)
    with open(dest_path, 'w') as f:
        f.write(embed_spec)

    # Pass relevant info into the template and append to the output
    html = VGL_TEMPLATE.render(div_id=node['div_id'],
                               filename=filename)
    self.body.append(html)
    raise nodes.SkipNode


def generic_visit_altair_plot(self, node):
    # TODO: figure out PNGs and insert them here
    if 'alt' in node.attributes:
        self.body.append(_('[ graph: %s ]') % node['alt'])
    else:
        self.body.append(_('[ graph ]'))
    raise nodes.SkipNode


def setup(app):
    setup.app = app
    setup.config = app.config
    setup.confdir = app.confdir

    app.add_node(altair_plot,
                 html=(html_visit_altair_plot, None),
                 latex=(generic_visit_altair_plot, None),
                 texinfo=(generic_visit_altair_plot, None),
                 text=(generic_visit_altair_plot, None),
                 man=(generic_visit_altair_plot, None))

    app.add_directive('altair-plot', AltairPlotDirective)
    app.add_directive('altair-plot-setup', AltairPlotSetupDirective)
    app.connect('env-purge-doc', purge_altair_plot_setup)

    return {'version': '0.1'}
