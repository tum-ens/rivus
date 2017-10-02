# -*- coding: utf-8 -*-

import os
pdir = os.path.dirname
import sys
# Environment variable to know if the docs are being built on rtd.
on_rtd = os.environ.get('READTHEDOCS', None) == 'True'
print
print("Building on ReadTheDocs: {}".format(on_rtd))
print
print("Current working directory: {}".format(os.path.abspath(os.curdir)))
print("Python: {}".format(sys.executable))

rivus_path = os.path.abspath(pdir(pdir(__file__)))
print("Adding lib to path:\n{}".format(rivus_path))
sys.path.insert(0, rivus_path)

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.doctest',
    'sphinx.ext.intersphinx',
    'sphinx.ext.mathjax',
    'sphinx.ext.viewcode',
    'sphinx.ext.todo',
    # 'sphinx.ext.linkcode'
]

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = False

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
add_module_names = False

#templates_path = ['_templates']
source_suffix = '.rst'
master_doc = 'index'

project = u'rivus'
copyright = u'2015-2017, ojdo'
version = '0.1'
release = '0.1'

exclude_patterns = ['_build']
#pygments_style = 'sphinx'


# HTML output

htmlhelp_basename = 'rivusdoc'
if not on_rtd:
    try:
        import sphinx_rtd_theme
        html_theme = 'sphinx_rtd_theme'
        html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
    except Exception as e:
        html_theme = 'default'

html_theme_options = {
    'navigation_depth': 4,
}

# Include todos from ext.todo
todo_include_todos = True

# Add these to the end of all files: make it available from everywhere
rst_epilog = r"""
.. |m2| replace:: m\ :sup:`2`\

.. |br| raw:: html

   <br />

.. |hr| raw:: html

    <hr />
"""

# # Calculate repo link to source code
# tum = r'https://github.com/tum-ens/rivus'
# lnksz = r'https://github.com/lnksz/rivus/tree/havasi-playground'
# link_base = lnksz


# def linkcode_resolve(domain, info):
#     if domain != 'py':
#         return None
#     if not info['module']:
#         return None
#     filename = info['module'].replace('.', '/')
#     return link_base + "/%s.py" % filename


# LaTeX output

latex_elements = {
    'papersize': 'a4paper',
    'pointsize': '11pt',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    ('index', 'rivus.tex', u'rivus Documentation',
     u'ojdo', 'manual'),
]

# Manual page output

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('index', 'rivus', u'rivus Documentation',
     [u'ojdo'], 1)
]


# Texinfo output

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    ('index', 'rivus', u'rivus  Documentation',
     u'ojdo', 'rivus', 'A mixed integer linear optimisation model for energy infrastructure networks',
     'Miscellaneous'),
]


# Epub output

# Bibliographic Dublin Core info.
epub_title = u'rivus'
epub_author = u'ojdo'
epub_publisher = u'ojdo'
epub_copyright = u'2017, ojdo'

epub_exclude_files = ['search.html']


# Intersphinx

# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {
    'http://docs.python.org/': None,
    'pandas': ('http://pandas.pydata.org/pandas-docs/stable/', None),
    'matplotlib': ('http://matplotlib.org/', None)}
